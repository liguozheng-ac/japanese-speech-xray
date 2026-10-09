"""Typed inputs and structured results for the duration evidence layer."""
from dataclasses import dataclass
from enum import StrEnum

from speech_xray.reference.models import (
    ArtifactReference, ReferenceEntry, ReferenceManifest, ReferenceProfile,
    RateContext, NormalizedDuration,
)
from speech_xray.japanese.models import LongVowelSpan


class EvidenceStatus(StrEnum):
    OK = 'OK'
    ABSTAIN_INVALID_CANDIDATE = 'ABSTAIN_INVALID_CANDIDATE'
    ABSTAIN_REFERENCE_NOT_READY = 'ABSTAIN_REFERENCE_NOT_READY'
    ABSTAIN_TARGET_MISMATCH = 'ABSTAIN_TARGET_MISMATCH'
    ABSTAIN_INVALID_REFERENCE = 'ABSTAIN_INVALID_REFERENCE'
    ABSTAIN_MISSING_NORMALIZED_DURATION = 'ABSTAIN_MISSING_NORMALIZED_DURATION'
    ABSTAIN_REFERENCE_LEAKAGE = 'ABSTAIN_REFERENCE_LEAKAGE'


@dataclass(frozen=True)
class CandidateObservation:
    manifest: ReferenceManifest
    entry: ReferenceEntry
    original_span: LongVowelSpan
    rate: RateContext
    duration: NormalizedDuration


@dataclass(frozen=True)
class ReferenceObservation:
    profile: ReferenceProfile
    profile_artifact: ArtifactReference
    version: str
    origin_reference_set_id: str
    origin_profile_artifact: ArtifactReference


@dataclass(frozen=True)
class DeviationResult:
    status: EvidenceStatus
    reason_codes: tuple[str, ...]
    candidate: dict | None = None
    reference: dict | None = None
    evidence: dict | None = None

    def to_dict(self):
        from .duration import FORMULAS
        return {'schema_version':'0.1', 'representation':'LONG_VOWEL_DURATION_DEVIATION_EVIDENCE',
                'status':self.status, 'reason_codes':list(self.reason_codes),
                'primary_feature':'rate_normalized_duration', 'candidate':self.candidate,
                'reference':self.reference, 'evidence':self.evidence,
                'comparison_implementation':{'name':'SPEECH_XRAY_DURATION_DEVIATION','version':'0.1',
                    'derived_decimal_precision':50,'formulas':FORMULAS,
                    'feature_definition':{'raw_duration_ms':'ORIGINAL_UNSPLIT_LONG_VOWEL_INTERVAL_MILLISECONDS',
                        'rate_normalized_duration':'RAW_DURATION_OVER_MEAN_LINGUISTIC_MORA_PERIOD',
                        'rate_normalized_duration_per_mora':'RATE_NORMALIZED_DURATION_OVER_MORA_SPAN'},
                    'normalization_definition':{'implementation':'speech_xray.reference.normalization.normalize_duration',
                        'formula_version':'0.1','mean_mora_period_ms':'core_speech_duration_ms / mora_count',
                        'rate_context':'FIRST_TO_LAST_NONEMPTY_WORD_INCLUDING_INTERNAL_PAUSES'}},
                'interpretation':'DESCRIPTIVE_DISTRIBUTION_POSITION_ONLY'}

    def to_json(self):
        from .serialization import serialize
        return serialize(self.to_dict())
