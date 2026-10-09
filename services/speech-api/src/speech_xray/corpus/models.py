"""Pipeline availability and real-data readiness are separate from pronunciation."""

from dataclasses import asdict, dataclass
from enum import StrEnum


class SourceType(StrEnum):
    REAL_REFERENCE_RECORDING = "REAL_REFERENCE_RECORDING"
    TEST_FIXTURE = "TEST_FIXTURE"
    SYNTHETIC_AUDIO = "SYNTHETIC_AUDIO"
    EXTERNAL_RESEARCH_CORPUS = "EXTERNAL_RESEARCH_CORPUS"


class RecordingStatus(StrEnum):
    VALIDATED = "VALIDATED"
    REJECTED_INTAKE = "REJECTED_INTAKE"
    PLANNED = "PLANNED"
    REBUILD_REQUIRED = "REBUILD_REQUIRED"
    ALIGNMENT_FAILED = "ALIGNMENT_FAILED"
    MORA_MAPPING_FAILED = "MORA_MAPPING_FAILED"
    ACOUSTIC_EXTRACTION_FAILED = "ACOUSTIC_EXTRACTION_FAILED"
    REFERENCE_INTEGRITY_FAILED = "REFERENCE_INTEGRITY_FAILED"
    REFERENCE_READY = "REFERENCE_READY"


@dataclass(frozen=True)
class PromptTarget:
    target_id: str
    surface_hint: str
    expected_word_reading: str
    word_mora_indices: tuple[int, int]
    expected_reading_region: str
    expected_candidate_type: str
    orthographic_pattern: str
    expected_vowel_class: str
    expected_mora_span: int = 2

    def to_dict(self):
        return {**asdict(self), "word_mora_indices": list(self.word_mora_indices)}


@dataclass(frozen=True)
class Prompt:
    prompt_id: str
    text: str
    expected_reading: str
    expected_mora_count: int
    targets: tuple[PromptTarget, ...]


@dataclass(frozen=True)
class PromptPack:
    prompt_pack_id: str
    prompt_pack_version: int
    prompts: tuple[Prompt, ...]
    source: str
    sha256: str


@dataclass(frozen=True)
class Speaker:
    speaker_id: str
    source_type: SourceType
    self_reported_native_japanese: bool | None
    native_status_metadata_status: str


@dataclass(frozen=True)
class Session:
    session_id: str
    speaker_id: str
    prompt_pack_id: str
    prompt_pack_version: int
    prompt_pack_sha256: str
    consent_record_id: str | None
    consent_metadata_status: str
    permission_local_analysis: bool | None
    permission_derived_numeric_features: bool | None
    permission_public_raw_audio: bool = False
    permission_public_aggregate_statistics: bool = False


@dataclass(frozen=True)
class Recording:
    speaker_id: str
    session_id: str
    prompt_id: str
    take_id: str
    source_type: SourceType
    audio_path: str
    expected_audio_sha256: str | None
    evidence_receipt: str | None = None
    evidence_receipt_sha256: str | None = None

    @property
    def key(self):
        return f"{self.speaker_id}__{self.prompt_id}__{self.take_id}"


@dataclass(frozen=True)
class CorpusManifest:
    corpus_id: str
    corpus_root: str
    prompt_pack_id: str
    prompt_pack_version: int
    prompt_pack_sha256: str
    speakers: tuple[Speaker, ...]
    sessions: tuple[Session, ...]
    recordings: tuple[Recording, ...]
    external_reference_sets: tuple[tuple[str, str, str, str], ...]
    source: str
    sha256: str
    metadata_sources: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class IntakeOutcome:
    recording: Recording
    status: RecordingStatus
    reasons: tuple[str, ...]
    audio: object | None
    audio_sha256: str | None
    eligible_real_reference: bool

    def to_dict(self):
        return {"recording_id": self.recording.key, "speaker_id": self.recording.speaker_id,
                "session_id": self.recording.session_id, "prompt_id": self.recording.prompt_id,
                "take_id": self.recording.take_id, "source_type": self.recording.source_type,
                "status": self.status, "reasons": list(self.reasons), "audio_sha256": self.audio_sha256,
                "audio": self.audio.to_dict() if self.audio else None,
                "eligible_real_reference": self.eligible_real_reference}


@dataclass(frozen=True)
class TargetOutcome:
    target_id: str
    status: RecordingStatus
    reason: str
    reference_entry: object | None = None
    target_identity: object | None = None


@dataclass(frozen=True)
class BatchOutcome:
    intake: IntakeOutcome
    status: RecordingStatus
    reason: str
    outputs: tuple[tuple[str, str], ...]
    targets: tuple[TargetOutcome, ...] = ()

    def to_dict(self):
        return {"recording_id": self.intake.recording.key, "status": self.status, "reason": self.reason,
                "source_type": self.intake.recording.source_type,
                "eligible_real_reference": self.intake.eligible_real_reference, "outputs": dict(self.outputs),
                "targets": [{"target_id": t.target_id, "status": t.status, "reason": t.reason,
                             "span_id": t.reference_entry.span_id if t.reference_entry else None} for t in self.targets]}
