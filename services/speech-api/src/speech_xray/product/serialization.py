"""Explicit projection only; no arbitrary result object is exposed."""
from dataclasses import dataclass, field
from hashlib import sha256
from speech_xray.acoustics.models import evidence_json
from .models import SpeechXRayAnalysisResponse


def serialize(value):
    return evidence_json(value)


def identity(value):
    return sha256(serialize(value).encode('utf-8')).hexdigest()


@dataclass
class InternalAnalysisResult:
    public_evidence: dict
    stage_trace: list = field(default_factory=list)
    timings_ms: dict = field(default_factory=dict)
    private_debug: dict = field(default_factory=dict)


def project(result):
    # Enumerate the root boundary and validate every nested field. Debug stays local.
    keys = ('schema_version', 'analysis_id', 'analysis_fingerprint', 'status', 'prompt',
            'audio', 'timeline', 'targets', 'warnings', 'provenance')
    return SpeechXRayAnalysisResponse.model_validate({k: result.public_evidence[k] for k in keys})


def response_bytes(response):
    return serialize(response.model_dump(mode='python')).encode('utf-8')
