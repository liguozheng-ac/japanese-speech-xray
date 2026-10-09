"""Serializable measurements; source alignment timing remains Decimal."""

from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import StrEnum
import json

from speech_xray.japanese.models import LongVowelSpan
from .config import AcousticConfig


class ExtractionStatus(StrEnum):
    OK = "OK"
    NO_FRAMES = "NO_FRAMES"
    NO_VOICED_FRAMES = "NO_VOICED_FRAMES"
    SPAN_OUT_OF_AUDIO_RANGE = "SPAN_OUT_OF_AUDIO_RANGE"
    INVALID_SPAN = "INVALID_SPAN"
    INVALID_AUDIO = "INVALID_AUDIO"
    INSUFFICIENT_AUDIO_FOR_F0 = "INSUFFICIENT_AUDIO_FOR_F0"
    F0_CONFIG_UNSUPPORTED = "F0_CONFIG_UNSUPPORTED"
    F0_EXTRACTION_FAILED = "F0_EXTRACTION_FAILED"
    ENERGY_EXTRACTION_FAILED = "ENERGY_EXTRACTION_FAILED"
    PARTIAL_EVIDENCE = "PARTIAL_EVIDENCE"


def evidence_json(value) -> str:
    def encode(item):
        if isinstance(item, Decimal):
            if not item.is_finite():
                raise ValueError("Non-finite timing")
            return str(item)
        if isinstance(item, dict):
            return "{" + ", ".join(json.dumps(key) + ": " + encode(part) for key, part in item.items()) + "}"
        if isinstance(item, (tuple, list)):
            return "[" + ", ".join(encode(part) for part in item) + "]"
        return json.dumps(item, ensure_ascii=False, allow_nan=False)
    return encode(value) + "\n"


@dataclass(frozen=True)
class AudioMetadata:
    source: str
    sha256: str
    sample_rate_hz: int
    channels: int
    frame_count: int
    duration_ms: Decimal
    format: str
    subtype: str
    analysis_mono_strategy: str
    original_peak_abs_amplitude: float
    analysis_peak_abs_amplitude: float
    resampled: bool = False

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class AcousticFrame:
    index: int
    window_start_sample: int
    center_sample: int
    window_end_sample: int
    observed_start_sample: int
    observed_end_sample: int
    padding_left_samples: int
    padding_right_samples: int
    frame_start_ms: Decimal
    frame_center_ms: Decimal
    frame_end_ms: Decimal
    f0_hz: float | None
    voiced: bool | None
    voicing_probability: float | None
    rms: float

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class AcousticTrack:
    sample_rate_hz: int
    audio_frame_count: int
    frames: tuple[AcousticFrame, ...]
    extraction_status: ExtractionStatus
    f0_status: ExtractionStatus
    warnings: tuple[str, ...] = ()

    def to_dict(self):
        return {"sample_rate_hz": self.sample_rate_hz, "audio_frame_count": self.audio_frame_count,
                "extraction_scope": "WHOLE_UTTERANCE",
                "frame_count": len(self.frames), "extraction_status": self.extraction_status,
                "f0_status": self.f0_status, "warnings": list(self.warnings),
                "frames": [frame.to_dict() for frame in self.frames]}


@dataclass(frozen=True)
class MeasurementSummary:
    count: int = 0
    median: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    q25: float | None = None
    q75: float | None = None
    iqr: float | None = None

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class SampleInterval:
    sample_start: int
    sample_end: int
    sample_start_ms: Decimal
    sample_end_ms: Decimal

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class AcousticSpanEvidence:
    original_span: LongVowelSpan
    audio_sha256: str | None
    sample_interval: SampleInterval | None
    selected_frame_indices: tuple[int, ...]
    voiced_frame_count: int
    voiced_frame_ratio: float | None
    raw_f0_hz: MeasurementSummary
    rms: MeasurementSummary
    extraction_status: ExtractionStatus
    warnings: tuple[str, ...] = ()
    selected_window_observed_sample_interval: SampleInterval | None = None

    @property
    def frame_count(self):
        return len(self.selected_frame_indices)

    def to_dict(self):
        span = self.original_span
        return {"span_id": span.id, "candidate_id": span.candidate_id, "word_index": span.word_index,
                "phone_index": span.phone_index, "phone_label": span.phone_label,
                "mora_indices": list(span.mora_indices), "mora_span": span.mora_span,
                "vowel_class": span.vowel_class, "mapping_basis": span.mapping_basis,
                "alignment_start_ms": span.start_ms, "alignment_end_ms": span.end_ms,
                "alignment_duration_ms": span.duration_ms, "audio_sha256": self.audio_sha256,
                "sample_interval": self.sample_interval.to_dict() if self.sample_interval else None,
                "sample_interval_role": "QUANTIZED_ALIGNMENT_REFERENCE_NOT_DSP_CROP",
                "selected_window_observed_sample_interval": (
                    self.selected_window_observed_sample_interval.to_dict()
                    if self.selected_window_observed_sample_interval else None),
                "selected_frame_indices": list(self.selected_frame_indices), "frame_count": self.frame_count,
                "voiced_frame_count": self.voiced_frame_count, "voiced_frame_ratio": self.voiced_frame_ratio,
                "raw_f0_hz": self.raw_f0_hz.to_dict(), "rms": self.rms.to_dict(),
                "extraction_status": self.extraction_status, "warnings": list(self.warnings)}


@dataclass(frozen=True)
class AcousticEvidenceResult:
    audio_source: str
    mora_analysis_source: str
    mora_analysis_sha256: str | None
    alignment_source: str
    audio: AudioMetadata | None
    config: AcousticConfig
    library_versions: tuple[tuple[str, str], ...]
    track: AcousticTrack | None
    spans: tuple[AcousticSpanEvidence, ...]
    extraction_status: ExtractionStatus
    warnings: tuple[str, ...] = ()

    def to_dict(self):
        return {"schema_version": "0.1", "representation": "ACOUSTIC_EVIDENCE",
                "sources": {"audio": self.audio_source, "mora_analysis": self.mora_analysis_source,
                            "mora_analysis_sha256": self.mora_analysis_sha256,
                            "alignment_source": self.alignment_source},
                "audio": self.audio.to_dict() if self.audio else None,
                "extraction_config": self.config.to_dict(), "library_versions": dict(self.library_versions),
                "track": self.track.to_dict() if self.track else None,
                "span_evidence": [span.to_dict() for span in self.spans],
                "extraction_status": self.extraction_status, "warnings": list(self.warnings)}

    def to_json(self):
        return evidence_json(self.to_dict())
