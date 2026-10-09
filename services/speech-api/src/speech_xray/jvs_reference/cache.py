"""Strict control metadata and hash-verified immutable analysis receipts."""

import json
import math
from pathlib import Path

from speech_xray.reference.json_input import read_json
from speech_xray.corpus.batch_plan import digest
from speech_xray.corpus.validation import PRIVATE_ROOT


def safe_directory(path):
    path = Path(path).resolve()
    if not path.is_relative_to(PRIVATE_ROOT.resolve()):
        raise ValueError("REFERENCE_BUILD_MUST_REMAIN_PRIVATE")
    return path


def read_control(path):
    # Existing validation rejects duplicate keys and nonfinite JSON. Control
    # indices/settings use standard JSON types; feature input stays Decimal.
    _, identity = read_json(Path(path))
    raw = Path(path).read_bytes()
    import hashlib
    if hashlib.sha256(raw).hexdigest() != identity:
        raise ValueError("CONTROL_CHANGED_DURING_READ")
    def control_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("NONFINITE_CONTROL_NUMBER")
        return result
    return json.loads(raw.decode("utf-8-sig"), parse_float=control_float), identity


def validate_artifacts(receipt, signature):
    if receipt["signature"] != signature:
        raise ValueError("CACHE_CONFIGURATION_OR_INPUT_IDENTITY_MISMATCH")
    for artifact in receipt["artifacts"].values():
        path = safe_directory(artifact["path"])
        if digest(path) != artifact["sha256"]:
            raise ValueError("CACHE_ARTIFACT_IDENTITY_MISMATCH")
    if receipt.get("status") == "PASS":
        expected = {"audio", "transcript", "textgrid", "alignment", "mora_analysis", "acoustic_evidence"}
        if set(receipt["artifacts"]) != expected:
            raise ValueError("CACHE_COMPLETE_EVIDENCE_BUNDLE_REQUIRED")
        from speech_xray.alignment.textgrid_parser import parse_textgrid
        from speech_xray.japanese.alignment_input import load_alignment
        refs = receipt["artifacts"]
        parsed = parse_textgrid(Path(refs["textgrid"]["path"]))
        saved = load_alignment(refs["alignment"]["path"])
        if parsed != saved:
            raise ValueError("CACHE_TEXTGRID_PARSED_ALIGNMENT_MISMATCH")
    return receipt
