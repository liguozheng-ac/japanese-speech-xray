"""Immutable, private, hash-pinned experiment artifacts."""
from pathlib import Path
from speech_xray.reference.manifest import PROJECT_ROOT
from speech_xray.reference.json_input import read_json
from speech_xray.corpus.batch_plan import digest
from speech_xray.acoustics.models import evidence_json

ROOT = PROJECT_ROOT / 'data/private/controlled-perturbation'


def private(path):
    value = Path(path).resolve()
    if not value.is_relative_to(ROOT.resolve()):
        raise ValueError('STRESS_ARTIFACT_MUST_BE_PRIVATE')
    return value


def pin(path):
    path = Path(path).resolve()
    if not path.is_relative_to((PROJECT_ROOT / 'data/private').resolve()):
        raise ValueError('CORPUS_SOURCE_MUST_BE_PRIVATE')
    return {'path': str(path), 'sha256': digest(path)}


def verify(ref):
    if pin(ref['path']) != ref:
        raise ValueError('STRESS_SOURCE_IDENTITY_CHANGED')
    return Path(ref['path'])


def save(path, value):
    path = private(path)
    raw = evidence_json(value).encode('utf-8')
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError('IMMUTABLE_STRESS_ARTIFACT_CHANGED')
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(raw)
    return pin(path)


def load(path):
    return read_json(private(path))[0]
