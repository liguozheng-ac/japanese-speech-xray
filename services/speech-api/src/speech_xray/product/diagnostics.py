"""Bounded private failure receipts; never retain WAV, PCM, or model artifacts."""
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from uuid import uuid4
import wave

LOG = logging.getLogger('speech_xray.product')
MAX_REPORTS = 20
MAX_LOGS = 12
MAX_TAIL_BYTES = 16384


def _tail(path):
    with path.open('rb') as stream:
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(max(0, size - MAX_TAIL_BYTES))
        return stream.read(MAX_TAIL_BYTES).decode('utf-8', errors='replace')


def retain_alignment_failure(settings, folder, audio_path, returncode=None, exception=None):
    """Best effort: diagnostics must never replace the original execution failure."""
    try:
        root = settings.workspace_root.resolve().parent / 'alignment-failures'
        root.mkdir(parents=True, exist_ok=True)
        logs = []
        # The CLI transcript contains the exception; Kaldi logs explain input failures.
        candidates = [folder / 'alignment.log']
        candidates.extend(sorted((folder / 'mfa-temp').rglob('*.log')))
        for path in candidates:
            if len(logs) >= MAX_LOGS:
                break
            if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(folder.resolve()):
                logs.append({'file': path.relative_to(folder).as_posix(), 'tail': _tail(path)})
        with wave.open(str(audio_path), 'rb') as audio:
            metadata = {'channels': audio.getnchannels(), 'sample_width_bytes': audio.getsampwidth(),
                        'sample_rate_hz': audio.getframerate(), 'frame_count': audio.getnframes()}
        receipt = {'schema_version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
                   'workspace_id': folder.parent.name, 'alignment_step': folder.name,
                   'returncode': returncode, 'audio_metadata': metadata, 'logs': logs,
                   'exception': None if exception is None else
                   {'name': type(exception).__name__, 'message': str(exception)[:2048]}}
        path = root / f'alignment-failure-{uuid4().hex}.json'
        path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
        reports = sorted(root.glob('alignment-failure-*.json'), key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)
        for old in reports[MAX_REPORTS:]:
            old.unlink()
        LOG.error('alignment_failed workspace_id=%s step=%s returncode=%s diagnostic=%s',
                  folder.parent.name, folder.name, returncode, path.name)
        return path
    except Exception:
        LOG.exception('alignment_failure_diagnostics_failed workspace_id=%s', folder.parent.name)
        return None
