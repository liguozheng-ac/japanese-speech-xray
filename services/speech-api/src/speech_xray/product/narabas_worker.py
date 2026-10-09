"""Private JSONL worker. Runs only in the frozen Python 3.10 CPU environment."""
import contextlib
import json
import os
from pathlib import Path
import sys
import time


def main():
    repository, model_directory, home = sys.argv[1:]
    os.environ.setdefault("HOME", home)
    sys.path.insert(0, repository)
    protocol = sys.stdout

    def emit(value):
        protocol.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
        protocol.flush()

    # Library output must never enter the protocol. No audio/PCM is logged.
    with contextlib.redirect_stdout(sys.stderr):
        import narabas
        started = time.perf_counter()
        model = narabas.load_model(device="cpu", model_dir=model_directory)
        if model.sample_rate != 16000 or model.sess.get_providers() != ["CPUExecutionProvider"]:
            raise RuntimeError("UNEXPECTED_MODEL_PROCESSING_DOMAIN")
        emit({"type": "ready", "pid": os.getpid(), "sample_rate_hz": model.sample_rate,
              "hop_length": model.hop_length, "model_load_ms": (time.perf_counter()-started)*1000})
        for line in sys.stdin:
            request = json.loads(line)
            if request == {"operation": "shutdown"}:
                break
            identifier = request["id"]
            try:
                started = time.perf_counter()
                segments = model.align(request["audio_path"], request["phone_sequence"])
                emit({"type": "result", "id": identifier, "segments": segments,
                      "alignment_ms": (time.perf_counter()-started)*1000})
            except Exception as error:
                emit({"type": "error", "id": identifier, "error_class": type(error).__name__,
                      "error_message": str(error)[:2048]})


if __name__ == "__main__":
    main()
