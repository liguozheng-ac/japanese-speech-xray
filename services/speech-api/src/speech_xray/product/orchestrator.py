"""HTTP-independent request lifecycle, bounded execution and hard process deadline."""
from contextlib import contextmanager
from collections import OrderedDict
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import logging
import multiprocessing
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
from uuid import uuid4
from .errors import ProductError
from .serialization import project

LOG = logging.getLogger('speech_xray.product')


@dataclass(frozen=True)
class SpeechAnalysisRequest:
    audio_path: Path
    workspace: Path
    binding: object
    request_id: str
    config_version: str
    control_token: str = ''
    progress_connection: object = None


class CancellationControl:
    def __init__(self):
        self.requested = threading.Event()
        self.done = threading.Event()
        self.status = 'RUNNING'
        self.request_id = ''
        self.stage_index = 1
        self.updated_at = datetime.now(timezone.utc).isoformat()
        self.history = []
        self.state = 'RUNNING'


STAGES = ('音频准备', '主发音对齐', '声学证据与参考计算', '实现候选比较', '结果整理')


def report_stage(request, index):
    """Only runtime boundaries publish; this carries no audio or result data."""
    connection = getattr(request, 'progress_connection', None)
    if connection is not None:
        connection.send(('progress', (index, datetime.now(timezone.utc).isoformat())))


def worker(analyzer, request, connection):
    try:
        result = analyzer.analyse(replace(request, progress_connection=connection))
        connection.send(('result', result))
    except ProductError as error:
        connection.send(('error', (error.code, error.stage, error.reason)))
    except BaseException:
        LOG.exception('pipeline_failed request_id=%s', request.request_id)
        connection.send(('error', ('INTERNAL_PIPELINE_ERROR', 'PIPELINE', 'UNEXPECTED_FAILURE')))
    finally:
        connection.close()


def stop_process_tree(process):
    if not process.is_alive():
        process.join()
        return
    if os.name == 'nt':
        # Only the numeric PID of our own spawned worker; kills its MFA descendants too.
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        # Child forms its own session before launching subprocesses.
        import signal
        try: os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError: pass
    process.join(timeout=5)
    if process.is_alive():
        process.kill(); process.join()


def isolated_worker(analyzer, request, connection):
    if os.name != 'nt': os.setsid()
    worker(analyzer, request, connection)


class ProductOrchestrator:
    def __init__(self, settings, registry, analyzer):
        self.settings, self.registry, self.analyzer = settings, registry, analyzer
        self.stage_labels = getattr(analyzer,'stage_labels',STAGES)
        self.slots = threading.BoundedSemaphore(settings.max_concurrent_analyses)
        self.last_metrics = {}
        self.controls = OrderedDict()
        self.control_lock = threading.Lock()

    def update_progress(self, token, index, timestamp=None):
        with self.control_lock:
            control = self.controls.get(token)
            if control is None or control.done.is_set() or not 1 <= index <= 5 or index < control.stage_index:
                return
            control.stage_index = index
            control.updated_at = timestamp or datetime.now(timezone.utc).isoformat()
            if not control.history or control.history[-1]['stage_index'] != index:
                control.history.append({'stage_index': index, 'stage_label': self.stage_labels[index-1], 'updated_at': control.updated_at})

    def progress(self, token):
        with self.control_lock:
            c = self.controls.get(token)
            if c is None:
                return {'state': 'NOT_FOUND'}
            return {'request_key': token, 'request_id': c.request_id, 'stage_index': c.stage_index,
                    'stage_label': self.stage_labels[c.stage_index-1], 'updated_at': c.updated_at,
                    'state': c.state, 'history': [dict(item) for item in c.history]}

    def cancel(self, token, wait_seconds=3):
        with self.control_lock:
            control = self.controls.get(token)
            if control is None:
                return 'NOT_FOUND'
            if control.status == 'RUNNING':
                control.status = 'CANCEL_REQUESTED'
                control.requested.set()
        # done is set only after worker-tree termination, workspace cleanup and slot release.
        if not control.done.wait(wait_seconds):
            return 'CANCELLING' if control.requested.is_set() else 'FINISHING'
        return 'CANCELLED' if control.status == 'CANCELLED' else 'FINISHED'

    def check_cancelled(self, request):
        with self.control_lock:
            control = self.controls.get(request.control_token)
        if control and control.requested.is_set():
            raise ProductError('ANALYSIS_CANCELLED', 'PIPELINE', 'USER_CANCELLED')

    @contextmanager
    def session(self, prompt_id, request_id=None, control_token=None):
        binding = self.registry.resolve(prompt_id)
        if not self.slots.acquire(blocking=False):
            raise ProductError('SERVICE_BUSY', 'INPUT_VALIDATED', 'CAPACITY_OCCUPIED')
        request_id = request_id or str(uuid4())
        token = control_token or request_id
        control = CancellationControl()
        with self.control_lock:
            if token in self.controls:
                self.slots.release()
                raise ProductError('INVALID_REQUEST', 'INPUT_VALIDATED', 'CONTROL_TOKEN_REUSED')
            self.controls[token] = control
            control.request_id = request_id
        self.update_progress(token, 1)
        # Do not use even an internal caller's correlation ID as a filesystem path.
        folder = self.settings.workspace_root.resolve() / uuid4().hex
        try:
            folder.mkdir(parents=True)
            request = SpeechAnalysisRequest(folder / 'input.wav', folder, binding, request_id, self.settings.policy_version, token)
            LOG.info('request_started request_id=%s prompt_id=%s', request_id, prompt_id)
            yield request
        except ProductError as error:
            LOG.warning('request_failed request_id=%s workspace_id=%s code=%s stage=%s reason=%s',
                        request_id, folder.name, error.code, error.stage, error.reason)
            with self.control_lock:
                control.status = 'CANCELLED' if error.code == 'ANALYSIS_CANCELLED' else 'FINISHED'
                control.state = 'CANCELLED' if error.code == 'ANALYSIS_CANCELLED' else 'ERROR'
            raise
        except BaseException:
            with self.control_lock:
                control.state = 'ERROR'
            raise
        finally:
            try:
                if folder.exists() and not self.settings.debug_retention:
                    if folder.parent != self.settings.workspace_root.resolve():
                        raise RuntimeError('WORKSPACE_SCOPE_CHANGED')
                    shutil.rmtree(folder)
                LOG.info('cleanup request_id=%s retained=%s', request_id, self.settings.debug_retention)
            except BaseException:
                with self.control_lock:
                    control.status = 'FINISHED'  # Do not acknowledge a clean cancellation.
                    control.state = 'ERROR'
                raise
            finally:
                self.slots.release()
                with self.control_lock:
                    if control.status != 'CANCELLED':
                        control.status = 'FINISHED'
                    if control.state == 'RUNNING':
                        control.state = 'FINISHED'
                    control.updated_at = datetime.now(timezone.utc).isoformat()
                    control.done.set()
                    # Bounded in-memory tombstones support retries without retaining audio.
                    for old_token in list(self.controls):
                        if len(self.controls) <= 128:
                            break
                        if self.controls[old_token].done.is_set():
                            del self.controls[old_token]

    def analyse(self, request):
        if getattr(self.analyzer,'persistent_execution',False):
            return self._analyse_persistent(request)
        context = multiprocessing.get_context('spawn')
        parent, child = context.Pipe(duplex=False)
        process = context.Process(target=isolated_worker, args=(self.analyzer, request, child), daemon=False)
        started = time.monotonic()
        try:
            self.check_cancelled(request)
            process.start(); child.close()
            while True:
                self.check_cancelled(request)
                remaining = self.settings.timeout_seconds - (time.monotonic()-started)
                if remaining <= 0:
                    raise ProductError('ANALYSIS_TIMEOUT', 'PIPELINE', 'EXECUTION_LIMIT')
                if parent.poll(min(0.1, remaining)):
                    try: kind, value = parent.recv()
                    except EOFError as error:
                        raise ProductError('INTERNAL_PIPELINE_ERROR', 'PIPELINE', 'WORKER_EXITED') from error
                    if kind == 'progress':
                        self.update_progress(request.control_token, *value)
                        continue
                    break
            self.check_cancelled(request)
            if kind == 'error': raise ProductError(*value)
            self.update_progress(request.control_token, 5)
            response = project(value)
            # Completion and cancel compete under one lock; a completed result is never
            # retroactively labelled cancelled by a late control request.
            with self.control_lock:
                control = self.controls[request.control_token]
                if control.requested.is_set():
                    raise ProductError('ANALYSIS_CANCELLED', 'PIPELINE', 'USER_CANCELLED')
                control.status = 'FINISHED'
            self.last_metrics = {'request_id': request.request_id, 'timings_ms': value.timings_ms,
                                 'stage_trace': value.stage_trace, 'private_audit':value.private_debug}
            for entry in value.stage_trace:
                LOG.info('stage request_id=%s stage=%s reason_code=%s', request.request_id,
                         entry['stage'], entry['reason_code'])
            LOG.info('request_completed request_id=%s status=%s', request.request_id, response.status)
            return response
        finally:
            if process.pid is not None:
                process.join(timeout=0.5)
                stop_process_tree(process)
            parent.close(); child.close()

    def _analyse_persistent(self, request):
        # HTTP already runs this method off the event loop. The shared model process
        # survives requests. Cancellation waits for current inference/DSP to return;
        # the workspace and heavy slot remain owned until then.
        started = time.monotonic()
        service = self
        def check_active():
            service.check_cancelled(request)
            if time.monotonic()-started > service.settings.timeout_seconds:
                raise ProductError('ANALYSIS_TIMEOUT','PIPELINE','EXECUTION_LIMIT')
        class Progress:
            def send(self, message):
                check_active()
                kind,value = message
                if kind != 'progress': raise RuntimeError('INVALID_PROGRESS_MESSAGE')
                service.update_progress(request.control_token,*value)
        try:
            check_active()
            value = self.analyzer.analyse(replace(request,progress_connection=Progress()))
            check_active()
            response = project(value)
            with self.control_lock:
                control = self.controls[request.control_token]
                if control.requested.is_set():
                    raise ProductError('ANALYSIS_CANCELLED','PIPELINE','USER_CANCELLED')
                control.status = 'FINISHED'
            self.last_metrics = {'request_id':request.request_id,'timings_ms':value.timings_ms,
                                 'stage_trace':value.stage_trace,'private_audit':value.private_debug}
            self.update_progress(request.control_token,5)
            return response
        except BaseException:
            self.check_cancelled(request)
            raise
