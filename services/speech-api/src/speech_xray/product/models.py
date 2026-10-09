"""Versioned, finite public evidence. Decimal JSON is emitted by serialization.py."""
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, WithJsonSchema

Number = Annotated[Decimal, Field(allow_inf_nan=False), WithJsonSchema({'type':'number'})]
Time = Annotated[Decimal, Field(ge=0, allow_inf_nan=False), WithJsonSchema({'type':'number','minimum':0})]
Index = Annotated[int, Field(ge=0)]
Sha256 = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Status = Literal['COMPLETED', 'PARTIAL_EVIDENCE', 'ABSTAINED']
EvidenceStatus = Literal['AVAILABLE', 'PARTIAL', 'UNAVAILABLE', 'ABSTAINED']


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class Reason(Model):
    stage: str
    reason_code: str
    message: str


class Prompt(Model):
    prompt_id: str
    display_text: str
    language: Literal['ja'] = 'ja'
    prompt_version: str


class PromptCatalog(Model):
    prompt_pack_version: str
    prompts: list[Prompt]


class Audio(Model):
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    duration_ms: Time
    sample_rate_hz: int = Field(gt=0)
    channels: int = Field(gt=0)
    sample_count: int = Field(gt=0)
    decoded_format: Literal['WAV']


class TimeSpan(Model):
    start_ms: Time
    end_ms: Time

    @model_validator(mode='after')
    def ordered(self):
        if self.end_ms < self.start_ms:
            raise ValueError('Reversed time span')
        return self


class Word(TimeSpan):
    index: Index
    surface: str
    reading: str | None


class Phone(TimeSpan):
    index: Index
    symbol: str
    word_index: Index | None


class Mora(Model):
    index: Index
    word_index: Index
    word_mora_index: Index
    representation: str
    kind: str
    shared_span: TimeSpan | None
    timing_basis: Literal['SHARED_ORIGINAL_LONG_PHONE', 'NO_INDIVIDUAL_ACOUSTIC_BOUNDARY', 'SHARED_NATIVE_PHONE_ENVELOPE']


class Timeline(TimeSpan):
    basis: Literal['PRIMARY_ANALYSIS_ALIGNMENT'] = 'PRIMARY_ANALYSIS_ALIGNMENT'
    words: list[Word]
    phones: list[Phone]
    morae: list[Mora]

    @model_validator(mode='after')
    def validate_tiers(self):
        for tier in (self.words, self.phones):
            previous = self.start_ms
            for item in tier:
                if item.start_ms < previous or item.end_ms > self.end_ms:
                    raise ValueError('Timeline order/domain mismatch')
                previous = item.end_ms
        word_indices = {w.index for w in self.words}
        if any(p.word_index is not None and p.word_index not in word_indices for p in self.phones):
            raise ValueError('Unowned phone')
        if any(m.word_index not in word_indices for m in self.morae):
            raise ValueError('Unowned mora')
        return self


class Duration(Model):
    raw_duration_ms: Number
    rate_normalized_duration: Number
    rate_normalized_duration_per_mora: Number
    normalization_version: Literal['0.1'] = '0.1'


class Reference(Model):
    target_id: str
    version: str
    profile_sha256: str
    independent_speaker_count: int = Field(gt=0)
    primary_feature: Literal['rate_normalized_duration'] = 'rate_normalized_duration'
    median: Number
    mad: Number
    q25: Number
    q75: Number
    iqr: Number
    minimum: Number
    maximum: Number
    readiness: str


class Deviation(Model):
    signed_delta: Number
    ratio_to_median: Number
    mad_distance: Number | None
    direction: Literal['BELOW_REFERENCE_MEDIAN', 'AT_REFERENCE_MEDIAN', 'ABOVE_REFERENCE_MEDIAN']
    inside_iqr: bool
    inside_observed_min_max: bool
    warnings: list[str]
    formula_version: Literal['0.1'] = '0.1'


class Realization(Model):
    canonical_pronunciation: list[str]
    experimental_reduced_pronunciation: list[str] | None
    selected_variant: Literal['CANONICAL_SELECTED', 'REDUCED_SELECTED', 'AMBIGUOUS_OR_UNRESOLVED', 'ALIGNMENT_FAILED']
    variant_identity_status: str
    evidence_status: EvidenceStatus
    interpretation: Literal['EXPERIMENTAL_ENGINEERING_PROBE'] = 'EXPERIMENTAL_ENGINEERING_PROBE'
    hypothesis_version: Literal['0.1'] = '0.1'


class Acoustics(Model):
    selected_frame_count: Index
    voiced_frame_count: Index
    raw_f0_median_hz: Number | None
    rms_median: Number | None
    extraction_status: str
    f0_interpretation: Literal['RAW_ACOUSTIC_MEASUREMENT'] = 'RAW_ACOUSTIC_MEASUREMENT'


class Availability(Model):
    duration: bool
    reference: bool
    deviation: bool
    realization: bool
    raw_f0: bool
    rms: bool


class Target(Model):
    target_id: str
    surface: str
    reading: str
    word_index: Index | None
    mora_indices: list[Index]
    mora_span: Literal[2] = 2
    vowel_class: Literal['A', 'I', 'U', 'E', 'O']
    mapping_basis: Literal['PROLONGED_MARK', 'KANA_SEQUENCE']
    time_span: TimeSpan | None
    duration: Duration | None
    reference: Reference | None
    deviation: Deviation | None
    realization: Realization | None
    acoustics: Acoustics | None
    availability: Availability
    evidence_status: EvidenceStatus
    reasons: list[Reason]


class AlignmentProvenance(Model):
    aligner_commit: str = Field(pattern=r'^[0-9a-f]{40}$')
    model_sha256: Sha256
    phone_sequence_version: Literal['narabas-ja-1.0.0']
    phone_sequence_sha256: Sha256
    alignment_sample_rate_hz: Literal[16000]
    resample_method: Literal['SCIPY_RESAMPLE_POLY_PCM16_1.0.0']
    runtime_lock_sha256: Sha256


class Provenance(Model):
    pipeline_version: Literal['product-m1-1.0.0','product-m1-1.1.0'] = 'product-m1-1.0.0'
    analysis_policy_version: str
    prompt_binding_version: str
    prompt_binding_sha256: str
    prompt_pack_sha256: str
    reference_version: str = 'task009-v2'
    deviation_version: Literal['0.1'] = '0.1'
    realization_version: Literal['0.1'] = '0.1'
    alignment_engine: Literal['MFA_CPU_CLI','NARABAS_CPU_WORKER'] = 'MFA_CPU_CLI'
    alignment_engine_version: str
    acoustic_model_sha256: Sha256
    dictionary_sha256: Sha256 | None
    g2p_model_sha256: Sha256 | None
    runtime_identity_sha256: Sha256
    alignment_provenance: AlignmentProvenance | None = None
    compatibility_policy: Literal['EXACT_SURFACE_READING_LOCAL_MORA_VOWEL_BASIS_FEATURE_V1'] = 'EXACT_SURFACE_READING_LOCAL_MORA_VOWEL_BASIS_FEATURE_V1'
    sentence_context_equivalence_validated: Literal[False] = False
    candidate_audio_in_reference: bool
    comparison_role: Literal['DESCRIPTIVE_ONLY', 'IN_POPULATION_NATIVE_INTEGRATION_SMOKE']
    real_labelled_learner_data_ready: Literal[False] = False
    calibrated_diagnosis_ready: Literal[False] = False
    cross_condition_likelihood_comparable: Literal[False] = False

    @model_validator(mode='after')
    def measurement_pairing(self):
        from .measurement_registry import require_pair
        entry = require_pair(self.alignment_engine,self.reference_version,self.pipeline_version)
        if self.alignment_engine == 'MFA_CPU_CLI':
            if self.dictionary_sha256 is None or self.g2p_model_sha256 is None or self.alignment_provenance is not None:
                raise ValueError('MFA_RESOURCE_PROVENANCE_REQUIRED')
        else:
            if self.dictionary_sha256 is not None or self.g2p_model_sha256 is not None or self.alignment_provenance is None:
                raise ValueError('NARABAS_NATIVE_PROVENANCE_REQUIRED_NO_MFA_RESOURCES')
            expected = entry['alignment_provenance']
            if self.alignment_provenance.model_dump() != expected or self.acoustic_model_sha256 != expected['model_sha256']:
                raise ValueError('NARABAS_FROZEN_ALIGNMENT_PROVENANCE_MISMATCH')
            if self.runtime_identity_sha256 != expected['runtime_lock_sha256']:
                raise ValueError('NARABAS_RUNTIME_IDENTITY_MISMATCH')
        return self


class SpeechXRayAnalysisResponse(Model):
    schema_version: Literal['1.0.0','1.1.0'] = '1.0.0'
    analysis_id: str
    analysis_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    status: Status
    prompt: Prompt
    audio: Audio
    timeline: Timeline | None
    targets: list[Target]
    warnings: list[Reason]
    provenance: Provenance

    @model_validator(mode='after')
    def evidence_consistency(self):
        from .measurement_registry import measurement
        entry = measurement(self.provenance.reference_version)
        if self.schema_version != entry['schema_version']:
            raise ValueError('SCHEMA_MEASUREMENT_VERSION_MISMATCH')
        native = self.provenance.alignment_engine == 'NARABAS_CPU_WORKER'
        if not self.targets:
            raise ValueError('Declared targets cannot disappear')
        for target in self.targets:
            # Historical authored MFA fixtures use a structural reference label.
            # Actual MFA resources are still hash-checked by ReferenceStore/runtime.
            if native and target.reference and target.reference.version != self.provenance.reference_version:
                raise ValueError('TARGET_REFERENCE_MEASUREMENT_MISMATCH')
            if native and target.reference and entry['profile_sha256_by_target'].get(
                    target.reference.target_id) != target.reference.profile_sha256:
                raise ValueError('TARGET_FROZEN_REFERENCE_HASH_MISMATCH')
            if native and (target.realization is not None or target.availability.realization):
                raise ValueError('NARABAS_REALIZATION_PROBE_UNAVAILABLE')
            for channel in ('duration','reference','deviation','realization'):
                if getattr(target.availability,channel) and getattr(target,channel) is None:
                    raise ValueError('Available evidence must have a value')
            if target.evidence_status=='ABSTAINED' and not target.reasons:
                raise ValueError('Abstention needs a structured reason')
        if self.status=='COMPLETED' and any(t.evidence_status!='AVAILABLE' for t in self.targets):
            raise ValueError('Completed evidence must be available')
        if self.status=='ABSTAINED' and not any(t.evidence_status=='ABSTAINED' for t in self.targets):
            raise ValueError('Abstention must retain an abstained target')
        if self.timeline:
            forbidden = 'SHARED_ORIGINAL_LONG_PHONE' if native else 'SHARED_NATIVE_PHONE_ENVELOPE'
            if any(m.timing_basis == forbidden for m in self.timeline.morae):
                raise ValueError('TIMING_BASIS_MEASUREMENT_MISMATCH')
        return self


class ErrorDetails(Model):
    stage: str | None = None
    reason_code: str | None = None


class ErrorResponse(Model):
    error_code: str
    message: str
    request_id: str
    details: ErrorDetails


class Live(Model):
    status: Literal['LIVE'] = 'LIVE'
    service: Literal['JapaneseSpeechXRay'] = 'JapaneseSpeechXRay'
    api_version: Literal['v1'] = 'v1'


class ReadinessComponent(Model):
    component: str
    ready: bool
    reason_code: str


class Ready(Model):
    status: Literal['READY', 'NOT_READY']
    components: list[ReadinessComponent]
    real_labelled_learner_data_ready: Literal[False] = False
    calibrated_diagnosis_ready: Literal[False] = False
