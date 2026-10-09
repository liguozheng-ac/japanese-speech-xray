"""Project-private immutable experiment artifacts, independent of stress modules."""
from pathlib import Path
from speech_xray.corpus.validation import PROJECT_ROOT
from speech_xray.corpus.batch_plan import digest
from speech_xray.reference.json_input import read_json
from speech_xray.acoustics.models import evidence_json

ROOT = PROJECT_ROOT / 'data/private/realization-experiments'


def private(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError('EXPERIMENT_OUTPUT_MUST_BE_PRIVATE')
    return path


def pin(path):
    path = Path(path).resolve()
    if not path.is_relative_to((PROJECT_ROOT / 'data/private').resolve()):
        raise ValueError('BENCHMARK_INPUT_MUST_BE_PRIVATE')
    return {'path': str(path), 'sha256': digest(path)}


def verify(ref):
    path = Path(ref['path'])
    if pin(path) != ref:
        raise ValueError('EXPERIMENT_ARTIFACT_CHANGED')
    return path


def load(path):
    return read_json(Path(path))[0]


def save(path, value):
    path = private(path); raw = evidence_json(value).encode('utf-8')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw: raise ValueError('IMMUTABLE_EXPERIMENT_ARTIFACT_CHANGED')
    else:
        with path.open('xb') as stream: stream.write(raw)
    return path
