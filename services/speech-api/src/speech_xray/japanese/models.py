"""Mora positions have no acoustic times; long-vowel spans own original times."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
import json

from speech_xray.alignment.models import exact_subtract


class VowelClass(StrEnum):
    A = "A"
    I = "I"
    U = "U"
    E = "E"
    O = "O"


class MoraKind(StrEnum):
    NORMAL = "NORMAL"
    LONG_VOWEL_EXTENSION = "LONG_VOWEL_EXTENSION"
    MORAIC_NASAL = "MORAIC_NASAL"
    GEMINATE = "GEMINATE"


class MappingBasis(StrEnum):
    PROLONGED_MARK = "PROLONGED_MARK"
    KANA_SEQUENCE = "KANA_SEQUENCE"


class UnresolvedReason(StrEnum):
    NO_READING = "NO_READING"
    UNSUPPORTED_KANA = "UNSUPPORTED_KANA"
    INVALID_PROLONGED_MARK = "INVALID_PROLONGED_MARK"
    NO_MATCHING_LONG_PHONE = "NO_MATCHING_LONG_PHONE"
    VOWEL_CLASS_MISMATCH = "VOWEL_CLASS_MISMATCH"
    AMBIGUOUS_PHONE_MAPPING = "AMBIGUOUS_PHONE_MAPPING"
    WORD_PHONE_BOUNDARY_MISMATCH = "WORD_PHONE_BOUNDARY_MISMATCH"
    UNSUPPORTED_PHONE = "UNSUPPORTED_PHONE"
    VOWEL_SEQUENCE_MISMATCH = "VOWEL_SEQUENCE_MISMATCH"
    NO_LONG_VOWEL_CANDIDATE = "NO_LONG_VOWEL_CANDIDATE"
    INTERNAL_SILENCE = "INTERNAL_SILENCE"
    NO_PHONE_EVIDENCE = "NO_PHONE_EVIDENCE"


@dataclass(frozen=True)
class ReadingPiece:
    surface: str
    reading: str
    is_oov: bool

    def to_dict(self):
        return {"surface": self.surface, "reading": self.reading, "is_oov": self.is_oov}


@dataclass(frozen=True)
class ReadingResult:
    surface: str
    reading: str | None
    pieces: tuple[ReadingPiece, ...] = ()
    reason: UnresolvedReason | None = None
    detail: str = ""
    source: str = "SUDACHI_CORE_SPLIT_B"

    @property
    def resolved(self):
        return self.reading is not None and self.reason is None


@dataclass(frozen=True)
class MoraToken:
    index: int
    word_index: int
    word_mora_index: int
    text: str
    reading: str
    kind: MoraKind
    vowel_class: VowelClass | None
    long_vowel_span_ids: tuple[str, ...] = ()

    def to_dict(self):
        return {"index": self.index, "word_index": self.word_index,
                "word_mora_index": self.word_mora_index, "text": self.text,
                "reading": self.reading, "kind": self.kind, "vowel_class": self.vowel_class,
                "long_vowel_span_ids": list(self.long_vowel_span_ids)}


@dataclass(frozen=True)
class TokenizationIssue:
    reason: UnresolvedReason
    character_index: int
    text: str
    detail: str


@dataclass(frozen=True)
class MoraTokenization:
    reading: str
    morae: tuple[MoraToken, ...]
    issue: TokenizationIssue | None = None


@dataclass(frozen=True)
class LongVowelCandidate:
    id: str
    word_index: int
    mora_indices: tuple[int, int]
    vowel_class: VowelClass
    mapping_basis: MappingBasis
    span_id: str | None = None

    def to_dict(self):
        return {"id": self.id, "word_index": self.word_index,
                "mora_indices": list(self.mora_indices), "mora_span": 2,
                "vowel_class": self.vowel_class, "mapping_basis": self.mapping_basis,
                "status": "MAPPED" if self.span_id else "UNRESOLVED", "span_id": self.span_id}


@dataclass(frozen=True)
class LongVowelSpan:
    id: str
    candidate_id: str
    word_index: int
    phone_index: int
    phone_label: str
    start_ms: Decimal
    end_ms: Decimal
    mora_indices: tuple[int, int]
    vowel_class: VowelClass
    mapping_basis: MappingBasis
    native_phone_indices: tuple[int, ...] = ()
    native_phone_labels: tuple[str, ...] = ()

    @property
    def duration_ms(self):
        return exact_subtract(self.end_ms, self.start_ms)

    @property
    def mora_span(self):
        return len(self.mora_indices)

    def to_dict(self):
        return {"id": self.id, "candidate_id": self.candidate_id,
                "word_index": self.word_index, "phone_index": self.phone_index,
                "phone_label": self.phone_label, "start_ms": self.start_ms,
                "end_ms": self.end_ms, "duration_ms": self.duration_ms,
                "mora_indices": list(self.mora_indices), "mora_span": self.mora_span,
                "vowel_class": self.vowel_class, "mapping_basis": self.mapping_basis,
                **({"native_phone_indices": list(self.native_phone_indices),
                    "native_phone_labels": list(self.native_phone_labels),
                    "timing_basis": "SHARED_NATIVE_PHONE_ENVELOPE"} if self.native_phone_indices else {})}


@dataclass(frozen=True)
class UnresolvedItem:
    reason: UnresolvedReason
    word_index: int | None
    detail: str
    candidate_id: str | None = None
    mora_indices: tuple[int, ...] = ()
    phone_indices: tuple[int, ...] = ()
    phone_labels: tuple[str, ...] = ()

    def to_dict(self):
        return {"reason": self.reason, "word_index": self.word_index, "detail": self.detail,
                "candidate_id": self.candidate_id, "mora_indices": list(self.mora_indices),
                "phone_indices": list(self.phone_indices), "phone_labels": list(self.phone_labels)}


@dataclass(frozen=True)
class WordAnalysis:
    index: int
    alignment_word_index: int
    surface: str
    reading_result: ReadingResult
    start_ms: Decimal
    end_ms: Decimal
    mora_indices: tuple[int, ...]
    phone_indices: tuple[int, ...]
    mapping_status: str
    unresolved_reasons: tuple[UnresolvedReason, ...]

    def to_dict(self):
        return {"index": self.index, "alignment_word_index": self.alignment_word_index,
                "surface": self.surface, "reading": self.reading_result.reading,
                "reading_status": "RESOLVED" if self.reading_result.resolved else "UNRESOLVED",
                "reading_source": self.reading_result.source,
                "reading_pieces": [piece.to_dict() for piece in self.reading_result.pieces],
                "start_ms": self.start_ms, "end_ms": self.end_ms,
                "mora_indices": list(self.mora_indices), "phone_indices": list(self.phone_indices),
                "mapping_status": self.mapping_status,
                "unresolved_reasons": list(self.unresolved_reasons)}


@dataclass(frozen=True)
class MoraAnalysisResult:
    alignment_source: str
    words: tuple[WordAnalysis, ...]
    morae: tuple[MoraToken, ...]
    long_vowel_candidates: tuple[LongVowelCandidate, ...]
    long_vowel_spans: tuple[LongVowelSpan, ...]
    unresolved_items: tuple[UnresolvedItem, ...]
    phone_adapter: str = "JAPANESE_MFA_V3_0_0"

    def to_dict(self):
        return {"schema_version": "0.2" if self.phone_adapter == "NARABAS_JA_1_0_0" else "0.1", "representation": "JAPANESE_MORA_LONG_VOWEL",
                "alignment_source": self.alignment_source,
                "phone_adapter": self.phone_adapter,
                **{key: [item.to_dict() for item in getattr(self, key)]
                   for key in ("words", "morae", "long_vowel_candidates",
                               "long_vowel_spans", "unresolved_items")}}

    def to_json(self):
        # Same numeric policy as TASK-002: never cast Decimal to binary float.
        def encode(value):
            if isinstance(value, Decimal):
                if not value.is_finite():
                    raise ValueError("Non-finite acoustic boundary")
                return str(value)
            if isinstance(value, dict):
                return "{" + ", ".join(json.dumps(key) + ": " + encode(item)
                                       for key, item in value.items()) + "}"
            if isinstance(value, list):
                return "[" + ", ".join(encode(item) for item in value) + "]"
            return json.dumps(value, ensure_ascii=False, allow_nan=False)
        return encode(self.to_dict()) + "\n"
