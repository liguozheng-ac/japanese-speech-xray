"""Private finite Decimal artifacts; immutable canonical UTF-8/LF bytes."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from speech_xray.acoustics.models import evidence_json
from speech_xray.corpus.validation import PRIVATE_ROOT
from speech_xray.reference.json_input import read_json
from speech_xray.reference.models import ArtifactReference

ROOT = PRIVATE_ROOT / 'learner-evaluation'


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:raise ValueError('DUPLICATE_EVALUATION_KEY')
        result[key] = value
    return result


def _constant(value):raise ValueError('NONFINITE_EVALUATION_NUMBER')


def decode(value):
    return json.loads(value,parse_int=Decimal,parse_float=Decimal,
                      parse_constant=_constant,object_pairs_hook=_unique)


def serialize(value):return evidence_json(value)


def identity(value):return hashlib.sha256(serialize(value).encode('utf-8')).hexdigest()


def private_path(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT.resolve()):raise ValueError('EVALUATION_PATH_MUST_REMAIN_PRIVATE')
    return path


def save(path, value):
    path = private_path(path)
    raw = serialize(value).encode('utf-8')
    if path.exists():
        if path.read_bytes() != raw:raise ValueError('EVALUATION_IMMUTABLE_ARTIFACT_CHANGED')
    else:
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(raw)
    return ArtifactReference(str(path),hashlib.sha256(raw).hexdigest())
