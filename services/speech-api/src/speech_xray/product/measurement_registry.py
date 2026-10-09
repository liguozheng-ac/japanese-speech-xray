"""Fail-closed pairing of frozen measurement engines, pipelines and references."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
REGISTRY = ROOT / "data/references/measurement-registry.json"


def measurement(version):
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if set(payload) != {"registry_version","measurements"} or payload["registry_version"] != "1.0.0":
        raise ValueError("UNSUPPORTED_MEASUREMENT_REGISTRY")
    try:
        value = payload["measurements"][version]
    except KeyError as error:
        raise ValueError("UNKNOWN_REFERENCE_MEASUREMENT_IDENTITY") from error
    if set(value) != {"alignment_engine","pipeline_version","schema_version","profile_sha256_by_target","alignment_provenance","population_review"}:
        raise ValueError("INVALID_MEASUREMENT_REGISTRY_ENTRY")
    if value['population_review'] not in {'ACCEPTED','PENDING'}:
        raise ValueError('INVALID_POPULATION_REVIEW_STATE')
    return value


def require_pair(engine, reference_version, pipeline_version):
    value = measurement(reference_version)
    if (engine,pipeline_version) != (value["alignment_engine"],value["pipeline_version"]):
        raise ValueError("CROSS_ALIGNER_REFERENCE_COMPARISON_FORBIDDEN")
    return value
