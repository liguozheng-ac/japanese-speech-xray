"""Small strict schema helpers; no additional schema/dependency framework."""

from pathlib import Path
import re

from speech_xray.reference.manifest import PROJECT_ROOT, keys, sha256, text
from speech_xray.reference.numeric import integer
from speech_xray.reference.json_input import read_json

PRIVATE_ROOT = PROJECT_ROOT / "data/private"


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", value):
        raise ValueError("INVALID_PSEUDONYMOUS_OR_PROMPT_ID")
    return value


def boolean_or_missing(value):
    if value is not None and type(value) is not bool:
        raise ValueError("EXPECTED_BOOLEAN_OR_UNVERIFIED_NULL")
    return value


def private_path(value, base: Path, boundary: Path):
    path = (base / text(value, "private path")).resolve()
    if not path.is_relative_to(boundary.resolve()) or not path.is_relative_to(PRIVATE_ROOT.resolve()):
        raise ValueError("PRIVATE_PATH_ESCAPE")
    return path


def pinned_json(ref, base: Path, boundary: Path):
    keys(ref, ("path", "sha256"))
    path = private_path(ref["path"], base, boundary)
    value, digest = read_json(path)
    if digest != sha256(ref["sha256"]):
        raise ValueError("MANIFEST_SOURCE_HASH_MISMATCH")
    return value, str(path), digest
