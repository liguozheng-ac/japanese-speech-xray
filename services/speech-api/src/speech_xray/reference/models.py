"""Reference observations retain each take; distributions count speakers only."""

from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import StrEnum

from speech_xray.acoustics.models import evidence_json
from speech_xray.japanese.models import LongVowelSpan


class ProfileStatus(StrEnum):
    READY_FOR_EXPERIMENT = "READY_FOR_EXPERIMENT"
    INSUFFICIENT_SPEAKERS = "INSUFFICIENT_SPEAKERS"
    NO_VALID_OBSERVATIONS = "NO_VALID_OBSERVATIONS"
    INTEGRITY_FAILURE = "INTEGRITY_FAILURE"
    PROMPT_MISMATCH = "PROMPT_MISMATCH"
    TARGET_MISMATCH = "TARGET_MISMATCH"
    INVALID_RATE_CONTEXT = "INVALID_RATE_CONTEXT"


@dataclass(frozen=True)
class ReferencePolicy:
    minimum_independent_speakers: int = 5

    def __post_init__(self):
        if type(self.minimum_independent_speakers) is not int or self.minimum_independent_speakers < 1:
            raise ValueError("minimum_independent_speakers must be a positive integer")


@dataclass(frozen=True)
class ArtifactReference:
    path: str
    sha256: str


@dataclass(frozen=True)
class TargetIdentity:
    target_id: str
    word_index: int
    word_mora_indices: tuple[int, int]
    phone_label: str
    vowel_class: str
    mora_span: int
    mapping_basis: str

    def to_dict(self):
        return {**asdict(self), "word_mora_indices": list(self.word_mora_indices)}


@dataclass(frozen=True)
class ReferenceEntry:
    prompt_id: str
    target_id: str
    speaker_id: str
    take_id: str
    utterance_id: str
    span_id: str
    sources: tuple[tuple[str, ArtifactReference], ...]

    def to_dict(self):
        return {"prompt_id": self.prompt_id, "target_id": self.target_id,
                "speaker_id": self.speaker_id, "take_id": self.take_id,
                "utterance_id": self.utterance_id, "span_id": self.span_id,
                "sources": {key: asdict(ref) for key, ref in self.sources}}


@dataclass(frozen=True)
class ReferenceManifest:
    reference_set_id: str
    prompt_id: str
    transcript_sha256: str
    target: TargetIdentity
    dataset: tuple[tuple[str, object], ...]
    creation_label: str
    entries: tuple[ReferenceEntry, ...]
    source: str
    sha256: str


@dataclass(frozen=True)
class RateContext:
    core_speech_start_ms: Decimal
    core_speech_end_ms: Decimal
    core_speech_duration_ms: Decimal
    mora_count: int
    utterance_mora_rate_per_second: Decimal
    mean_mora_period_ms: Decimal

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class NormalizedDuration:
    raw_duration_ms: Decimal
    rate_normalized_duration: Decimal
    rate_normalized_duration_per_mora: Decimal


@dataclass(frozen=True)
class TakeReferenceObservation:
    reference_set_id: str
    entry: ReferenceEntry
    original_span: LongVowelSpan
    rate: RateContext
    duration: NormalizedDuration

    def to_dict(self):
        return {"reference_set_id": self.reference_set_id, **self.entry.to_dict(),
                "audio_sha256": dict(self.entry.sources)["audio"].sha256,
                "original_span": self.original_span.to_dict(),
                "rate_context": self.rate.to_dict(), **asdict(self.duration)}


@dataclass(frozen=True)
class SpeakerReferenceObservation:
    speaker_id: str
    takes: tuple[TakeReferenceObservation, ...]
    medians: tuple[tuple[str, Decimal], ...]

    def to_dict(self):
        return {"speaker_id": self.speaker_id, "valid_take_count": len(self.takes),
                "aggregation": "MEDIAN_OF_TAKE_FEATURES",
                "feature_medians": dict(self.medians),
                "takes": [take.to_dict() for take in self.takes]}


@dataclass(frozen=True)
class RobustStatistics:
    count: int = 0
    median: Decimal | None = None
    mad: Decimal | None = None
    q25: Decimal | None = None
    q75: Decimal | None = None
    iqr: Decimal | None = None
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    scale_status: str = "NO_OBSERVATIONS"

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class RejectedObservation:
    entry: ReferenceEntry
    status: ProfileStatus
    reason: str

    def to_dict(self):
        return {**self.entry.to_dict(), "status": self.status, "reason": self.reason}


@dataclass(frozen=True)
class ReferenceProfile:
    manifest: ReferenceManifest
    policy: ReferencePolicy
    speakers: tuple[SpeakerReferenceObservation, ...]
    statistics: tuple[tuple[str, RobustStatistics], ...]
    rejected: tuple[RejectedObservation, ...]
    profile_status: ProfileStatus
    library_versions: tuple[tuple[str, str], ...]
    warnings: tuple[str, ...]

    def to_dict(self):
        return {"schema_version": "0.1", "representation": "PROMPT_TARGET_REFERENCE_PROFILE",
                "reference_set_id": self.manifest.reference_set_id, "prompt_id": self.manifest.prompt_id,
                "transcript_sha256": self.manifest.transcript_sha256,
                "target_id": self.manifest.target.target_id, "target": self.manifest.target.to_dict(),
                "dataset": dict(self.manifest.dataset),
                "speaker_count": len(self.speakers), "take_count": sum(len(s.takes) for s in self.speakers),
                "submitted_take_count": len(self.manifest.entries), "rejected_take_count": len(self.rejected),
                "independence_unit": "SPEAKER", "speaker_aggregation": "MEDIAN_OF_TAKE_FEATURES",
                "rate_definition": "FIRST_NONEMPTY_WORD_ONSET_TO_LAST_NONEMPTY_WORD_OFFSET_INCLUDING_INTERNAL_PAUSES",
                "normalization": {"rate_measure": "UTTERANCE_MORA_RATE", "formula_version": "0.1",
                    "mora_count": "ALL_VALID_LINGUISTIC_MORA_POSITIONS_WITH_COMPLETE_WORD_COVERAGE",
                    "utterance_mora_rate_per_second": "mora_count * 1000 / core_speech_duration_ms",
                    "mean_mora_period_ms": "core_speech_duration_ms / mora_count",
                    "rate_normalized_duration": "raw_duration_ms / mean_mora_period_ms",
                    "rate_normalized_duration_per_mora": "raw_duration_ms / (mean_mora_period_ms * mora_span)",
                    "derived_decimal_precision": 50},
                "statistics_implementation": {"name": "REFERENCE_FRACTION_LINEAR", "version": "0.1",
                    "quantiles": "LINEAR_(N-1)*P", "mad": "MEDIAN_ABSOLUTE_DEVIATION_UNSCALED",
                    "input_unit": "SPEAKER_FEATURE_MEDIAN", "outlier_removal": "NONE"},
                "minimum_independent_speakers": self.policy.minimum_independent_speakers,
                "readiness_policy_role": "CONFIGURABLE_PROTOTYPE_ENGINEERING_POLICY",
                "feature_statistics": {key: stats.to_dict() for key, stats in self.statistics},
                "speaker_observations": [speaker.to_dict() for speaker in self.speakers],
                "rejected_observations": [item.to_dict() for item in self.rejected],
                "profile_status": self.profile_status, "warnings": list(self.warnings),
                "source_provenance": {"manifest": {"path": self.manifest.source, "sha256": self.manifest.sha256},
                                      "library_versions": dict(self.library_versions)},
                "creation_metadata": {"label": self.manifest.creation_label,
                    "builder": "speech_xray.reference", "builder_version": "0.1",
                    "ordering": "SORTED_SPEAKER_ID_TAKE_ID", "wall_clock_timestamp": None}}

    def to_json(self):
        return evidence_json(self.to_dict())
