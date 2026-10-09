"""Immutable hypothesis identities and finite deterministic evidence serialization."""
from dataclasses import dataclass, asdict
from decimal import Decimal
from speech_xray.acoustics.models import evidence_json


def token(value):
    return isinstance(value, str) and bool(value) and not any(c.isspace() for c in value)


@dataclass(frozen=True)
class Target:
    target_id: str
    surface: str
    reading: str
    word_index: int
    word_mora_indices: tuple[int, int]
    vowel_class: str
    mapping_basis: str
    mora_span: int = 2

    def __post_init__(self):
        if (not all(token(x) for x in (self.target_id, self.surface, self.reading, self.mapping_basis))
                or type(self.word_index) is not int or self.word_index < 0
                or type(self.word_mora_indices) is not tuple or len(self.word_mora_indices) != 2
                or any(type(x) is not int or x < 0 for x in self.word_mora_indices)
                or self.word_mora_indices[1] != self.word_mora_indices[0] + 1
                or self.mora_span != 2 or self.vowel_class not in ('A', 'I', 'U', 'E', 'O')):
            raise ValueError('INVALID_EXPERIMENT_INPUT: target identity')


@dataclass(frozen=True)
class Hypotheses:
    target: Target
    canonical: tuple[str, ...]
    reduced: tuple[str, ...] | None
    phone_index: int
    status: str
    reasons: tuple[str, ...] = ()

    def __post_init__(self):
        if (not isinstance(self.target, Target) or type(self.canonical) is not tuple or not self.canonical
                or not all(token(x) for x in self.canonical) or type(self.phone_index) is not int
                or not 0 <= self.phone_index < len(self.canonical)):
            raise ValueError('INVALID_EXPERIMENT_INPUT: pronunciation')
        if self.reduced is not None:
            if (type(self.reduced) is not tuple or len(self.reduced) != len(self.canonical)
                    or not all(token(x) for x in self.reduced)
                    or [i for i, (a, b) in enumerate(zip(self.canonical, self.reduced)) if a != b] != [self.phone_index]
                    or self.status != 'EVIDENCE_AVAILABLE'):
                raise ValueError('INVALID_EXPERIMENT_INPUT: controlled replacement')
        elif self.status != 'UNSUPPORTED_REDUCED_HYPOTHESIS' or not self.reasons:
            raise ValueError('INVALID_EXPERIMENT_INPUT: unsupported hypothesis')

    def to_dict(self):
        return asdict(self)


STATUSES = frozenset(('EVIDENCE_AVAILABLE', 'UNSUPPORTED_REDUCED_HYPOTHESIS',
    'CANONICAL_ALIGNMENT_FAILED', 'REDUCED_ALIGNMENT_FAILED', 'COMPETITION_ALIGNMENT_FAILED',
    'AMBIGUOUS_VARIANT_IDENTITY', 'SCORE_NOT_COMPARABLE', 'INVALID_EXPERIMENT_INPUT'))


@dataclass(frozen=True)
class RealizationEvidence:
    hypotheses: Hypotheses
    canonical_alignment: dict | None
    reduced_alignment: dict | None
    competition_alignment: dict | None
    competition_selected_variant: str
    variant_identity_status: str
    boundary_displacements: dict | None
    alignment_scores: dict
    score_comparability: dict
    evidence_status: tuple[str, ...]
    abstention_reasons: tuple[str, ...]
    provenance: dict
    manipulation_context: dict | None = None
    duration_evidence: dict | None = None

    def __post_init__(self):
        if (not self.evidence_status or not set(self.evidence_status) <= STATUSES
                or self.competition_selected_variant not in ('CANONICAL_SELECTED', 'REDUCED_SELECTED',
                    'AMBIGUOUS_OR_UNRESOLVED', 'ALIGNMENT_FAILED')):
            raise ValueError('INVALID_EXPERIMENT_INPUT: evidence states')
        self.to_json()

    def to_dict(self):
        h = self.hypotheses
        result = asdict(self)
        del result['hypotheses']
        return {'schema_version': '0.1', 'target_identity': asdict(h.target),
                'canonical_pronunciation': list(h.canonical),
                'reduced_pronunciation': list(h.reduced) if h.reduced else None,
                'hypothesis_phone_index': h.phone_index, **result}

    def to_json(self):
        return evidence_json(self.to_dict())
