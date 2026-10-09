"""One CPU model process, serialized IPC, immutable resources, bounded recovery."""
from dataclasses import dataclass
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import uuid

COMMIT = "b5e6511ce24dd2f14fc633ed5a23214225ca3eb7"
MODEL_SHA256 = "ac9983740343b260e20f3ac72ee37c5f85a86436ff256c5701707f5909c4a126"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(4*1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class NarabasSpec:
    python: Path
    repository: Path
    model: Path
    lock: Path
    lock_sha256: str
    private_root: Path
    timeout_seconds: float = 120


class NarabasRuntime:
    def __init__(self, spec):
        self.spec = spec
        self.state = "STOPPED"
        self.process = None
        self.restarts = 0
        self.ready_receipt = None
        self._mutex = threading.Lock()
        self._messages = None
        self._stderr_tail = deque(maxlen=16)
        self._stderr_reader = None
        self._closed = False
        self._recovery_exhausted = False
        self._verify()

    def _verify(self):
        spec = self.spec
        if sha256(spec.model) != MODEL_SHA256 or sha256(spec.lock) != spec.lock_sha256:
            raise ValueError("NARABAS_RESOURCE_HASH_MISMATCH")
        locked = json.loads(spec.lock.read_text(encoding="utf-8"))
        root = spec.lock.parent.parent
        if any(sha256(root / name) != expected for name, expected in locked["files"].items()):
            raise ValueError("NARABAS_RUNTIME_FILE_CHANGED")
        def git(*args):
            return subprocess.check_output(["git", *args], cwd=spec.repository, text=True).strip()
        if (git("remote", "get-url", "origin") != "https://github.com/darashi/narabas.git"
                or git("rev-parse", "HEAD") != COMMIT or git("status", "--porcelain")):
            raise ValueError("NARABAS_OFFICIAL_SOURCE_LOCK_MISMATCH")

    def _receive(self):
        try:
            message = self._messages.get(timeout=self.spec.timeout_seconds)
        except queue.Empty as error:
            self.state = "ERROR"
            self._stop()
            raise TimeoutError("NARABAS_WORKER_TIMEOUT") from error
        if message is None:
            self.state = "ERROR"
            raise RuntimeError("NARABAS_WORKER_EXITED")
        return message

    def _start(self):
        if self._closed:
            raise RuntimeError("NARABAS_RUNTIME_CLOSED")
        self.state = "STARTING"
        spec = self.spec
        spec.private_root.mkdir(parents=True, exist_ok=True)
        # Keep at most 16 Ki characters of library diagnostics, never PCM/WAV.
        self._stderr_tail = deque(maxlen=16)
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        locked = json.loads(spec.lock.read_text(encoding="utf-8"))
        root = spec.lock.parent.parent
        environment["PATH"] = str(root / locked["python_base"] / "Library/bin") + os.pathsep + environment.get("PATH", "")
        self._messages = queue.Queue()
        self.process = subprocess.Popen([str(spec.python), "-u", str(Path(__file__).with_name("narabas_worker.py")),
                                         str(spec.repository), str(spec.model.parent), str(spec.private_root / "home")],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        encoding="utf-8", env=environment,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        process, messages = self.process, self._messages
        tail = self._stderr_tail
        def read_stderr():
            while chunk := process.stderr.read(1024):
                tail.append(chunk)
        self._stderr_reader = threading.Thread(target=read_stderr, daemon=True)
        self._stderr_reader.start()
        def read():
            try:
                for line in process.stdout:
                    messages.put(json.loads(line))
            finally:
                messages.put(None)
        threading.Thread(target=read, daemon=True).start()
        message = self._receive()
        if message.get("type") != "ready" or message.get("sample_rate_hz") != 16000:
            self.state = "ERROR"
            self._stop()
            raise RuntimeError("NARABAS_INVALID_HEALTH_RECEIPT")
        self.ready_receipt = message
        self.state = "READY"

    def align(self, audio_path, phone_sequence):
        with self._mutex:
            if self._recovery_exhausted:
                raise RuntimeError('NARABAS_WORKER_RECOVERY_EXHAUSTED')
            for attempt in range(2):
                try:
                    if self.process is None or self.process.poll() is not None:
                        self._start()
                    self.state = "BUSY"
                    identifier = uuid.uuid4().hex
                    self.process.stdin.write(json.dumps({"id": identifier, "audio_path": str(audio_path),
                                                         "phone_sequence": " ".join(phone_sequence)}) + "\n")
                    self.process.stdin.flush()
                    message = self._receive()
                    if message.get("id") != identifier:
                        raise RuntimeError("NARABAS_IPC_IDENTITY_MISMATCH")
                    self.state = "READY"
                    if message["type"] == "error":
                        raise ValueError(f"NARABAS_ALIGNMENT_ERROR:{message['error_class']}:{message['error_message']}")
                    return message
                except (RuntimeError, BrokenPipeError, OSError, TimeoutError):
                    self.state = "ERROR"
                    self._stop()
                    if self.restarts >= 1 or attempt == 1:
                        self._recovery_exhausted = True
                        raise
                    self.restarts += 1

    def _stop(self):
        if self.process:
            if self.process.poll() is None:
                if os.name == 'nt':
                    # A Windows venv python.exe can be a launcher with a child
                    # model interpreter. Terminate only our owned numeric PID tree.
                    subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   check=False, creationflags=subprocess.CREATE_NO_WINDOW)
                if self.process.poll() is None:
                    self.process.kill()
            self.process.wait(timeout=10)
            if self._stderr_reader:
                self._stderr_reader.join(timeout=2)
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                if stream:
                    stream.close()
        self.process = None
        self._stderr_reader = None
        self.spec.private_root.mkdir(parents=True, exist_ok=True)
        (self.spec.private_root / "worker-stderr.log").write_text(
            ''.join(self._stderr_tail)[-16384:], encoding='utf-8')

    def close(self):
        with self._mutex:
            self._closed = True
            if self.process and self.process.poll() is None:
                try:
                    self.process.stdin.write('{"operation":"shutdown"}\n')
                    self.process.stdin.flush()
                    self.process.wait(timeout=10)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            self._stop()
            self.state = "STOPPED"
