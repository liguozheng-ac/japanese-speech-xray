"""Use the existing finite Decimal JSON convention; canonical artifacts use LF."""
import hashlib
from pathlib import Path
from speech_xray.acoustics.models import evidence_json
from speech_xray.corpus.validation import PRIVATE_ROOT
from speech_xray.reference.models import ArtifactReference


def serialize(value):
    return evidence_json(value)


def save_canonical(path, value):
    path = Path(path).resolve()
    if not path.is_relative_to(PRIVATE_ROOT.resolve()):
        raise ValueError('DEVIATION_ARTIFACT_MUST_REMAIN_PRIVATE')
    encoded = serialize(value).encode('utf-8')
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError('CANONICAL_DEVIATION_OUTPUT_CHANGED')
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(encoded)
    return ArtifactReference(str(path), hashlib.sha256(encoded).hexdigest())
