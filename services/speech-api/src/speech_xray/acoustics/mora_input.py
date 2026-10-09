"""Read existing mapped spans and verify references without rediscovering kana rules."""

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from speech_xray.japanese.models import LongVowelSpan, MappingBasis, MoraAnalysisResult, VowelClass


@dataclass(frozen=True)
class MoraSpanInput:
    alignment_source: str
    long_vowel_spans: tuple[LongVowelSpan, ...]
    source: str = "IN_MEMORY_MORA_ANALYSIS"
    sha256: str | None = None

    @classmethod
    def from_analysis(cls, analysis: MoraAnalysisResult):
        return cls(analysis.alignment_source, analysis.long_vowel_spans)


def load_mora_analysis(path: str | Path) -> MoraSpanInput:
    def integer(value):
        if not isinstance(value, Decimal) or value < 0 or value != value.to_integral_value():
            raise ValueError("Expected nonnegative JSON integer reference")
        return int(value)

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate mora JSON key")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("Non-finite mora JSON numeric constant")

    source = Path(path).resolve()
    raw = source.read_bytes()
    value = json.loads(raw.decode("utf-8-sig"), parse_float=Decimal, parse_int=Decimal,
                       parse_constant=reject_constant, object_pairs_hook=unique_keys)
    expected = {"schema_version", "representation", "alignment_source", "phone_adapter", "words",
                "morae", "long_vowel_candidates", "long_vowel_spans", "unresolved_items"}
    if (not isinstance(value, dict) or set(value) != expected or value["schema_version"] not in {"0.1", "0.2"}
            or value["representation"] != "JAPANESE_MORA_LONG_VOWEL"):
        raise ValueError("Expected TASK-003 mora schema 0.1")
    native_mode = value["schema_version"] == "0.2"
    if native_mode and value["phone_adapter"] != "NARABAS_JA_1_0_0":
        raise ValueError("Unknown native envelope adapter")
    if not isinstance(value["alignment_source"], str) or not value["alignment_source"]:
        raise ValueError("Missing alignment_source")
    for name in ("words", "morae", "long_vowel_candidates", "long_vowel_spans", "unresolved_items"):
        if not isinstance(value[name], list):
            raise ValueError("Mora collections must be arrays")
    try:
        words = {integer(word["index"]): word for word in value["words"]}
        morae = {integer(mora["index"]): mora for mora in value["morae"]}
        candidates = {candidate["id"]: candidate for candidate in value["long_vowel_candidates"]}
        if (len(words) != len(value["words"]) or len(morae) != len(value["morae"])
                or len(candidates) != len(value["long_vowel_candidates"])):
            raise ValueError("Duplicate linguistic references")
        spans, ids, phones = [], set(), set()
        keys = {"id", "candidate_id", "word_index", "phone_index", "phone_label", "start_ms", "end_ms",
                "duration_ms", "mora_indices", "mora_span", "vowel_class", "mapping_basis"}
        if native_mode:
            keys |= {"native_phone_indices", "native_phone_labels", "timing_basis"}
        for item in value["long_vowel_spans"]:
            if set(item) != keys or not isinstance(item["id"], str) or not item["id"]:
                raise ValueError("Invalid long-vowel span schema")
            word_index, phone_index = integer(item["word_index"]), integer(item["phone_index"])
            indices = tuple(integer(index) for index in item["mora_indices"])
            if (len(indices) != 2 or indices[1] != indices[0] + 1 or integer(item["mora_span"]) != 2
                    or item["id"] in ids or phone_index in phones):
                raise ValueError("Duplicate or invalid mapped span references")
            if not isinstance(item["phone_label"], str) or not item["phone_label"]:
                raise ValueError("Empty phone label")
            if any(not isinstance(item[name], Decimal) or not item[name].is_finite()
                   for name in ("start_ms", "end_ms", "duration_ms")):
                raise ValueError("Span times must be finite Decimal")
            span = LongVowelSpan(item["id"], item["candidate_id"], word_index, phone_index,
                                 item["phone_label"], item["start_ms"], item["end_ms"], indices,
                                 VowelClass(item["vowel_class"]), MappingBasis(item["mapping_basis"]),
                                 tuple(integer(i) for i in item["native_phone_indices"]) if native_mode else (),
                                 tuple(item["native_phone_labels"]) if native_mode else ())
            if native_mode and (span.native_phone_indices != (phone_index,phone_index+1)
                    or span.native_phone_labels != (span.vowel_class.lower(),)*2
                    or item["timing_basis"] != "SHARED_NATIVE_PHONE_ENVELOPE"
                    or span.phone_label != span.vowel_class.lower()+"ː"):
                raise ValueError("Invalid native vowel envelope identity")
            if span.start_ms < 0 or span.end_ms < span.start_ms or span.duration_ms != item["duration_ms"]:
                raise ValueError("Invalid source span boundaries/duration")
            word, candidate = words[word_index], candidates[span.candidate_id]
            if (not word["start_ms"] <= span.start_ms <= span.end_ms <= word["end_ms"]
                    or phone_index not in word["phone_indices"] or candidate["status"] != "MAPPED"
                    or candidate["span_id"] != span.id or candidate["mora_indices"] != list(indices)
                    or candidate["word_index"] != word_index or candidate["vowel_class"] != span.vowel_class
                    or candidate["mapping_basis"] != span.mapping_basis):
                raise ValueError("Mapped span conflicts with its word/candidate provenance")
            if native_mode and not set(span.native_phone_indices) <= set(word["phone_indices"]):
                raise ValueError("Native envelope phones outside word")
            for index in indices:
                mora = morae[index]
                if (mora["word_index"] != word_index or index not in word["mora_indices"]
                        or span.id not in mora["long_vowel_span_ids"]):
                    raise ValueError("Mapped span conflicts with mora references")
            ids.add(span.id)
            phones.add(phone_index)
            spans.append(span)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("Malformed TASK-003 mapped span references") from error
    return MoraSpanInput(value["alignment_source"], tuple(spans), str(source), hashlib.sha256(raw).hexdigest())
