"""Consume TASK-002 JSON or its existing TextGrid parser, without changing alignment."""

from decimal import Decimal
import json
from pathlib import Path

from speech_xray.alignment.models import AlignmentResult, PhoneInterval, WordInterval
from speech_xray.alignment.textgrid_parser import parse_textgrid


def validate_alignment(result: AlignmentResult) -> None:
    def numeric(value):
        return isinstance(value, Decimal) and value.is_finite()

    if not isinstance(result.source, str) or not result.source:
        raise ValueError("Alignment source must be a nonempty string")
    if not numeric(result.start_ms) or not numeric(result.end_ms):
        raise ValueError("Alignment times must be finite Decimal numbers")
    if result.start_ms < 0 or result.end_ms < result.start_ms:
        raise ValueError("Invalid alignment time domain")
    for intervals in (result.words, result.phones):
        previous = result.start_ms
        for interval in intervals:
            if not isinstance(interval.label, str):
                raise ValueError("Interval label must be a string")
            if not numeric(interval.start_ms) or not numeric(interval.end_ms):
                raise ValueError("Interval times must be finite Decimal numbers")
            if (interval.start_ms < previous or interval.end_ms < interval.start_ms
                    or interval.end_ms > result.end_ms):
                raise ValueError("Out-of-range, overlapping or unordered alignment intervals")
            previous = interval.end_ms


def load_alignment(path: str | Path) -> AlignmentResult:
    path = Path(path)
    if path.suffix.casefold() == ".textgrid":
        result = parse_textgrid(path)
        validate_alignment(result)
        return result

    def no_duplicates(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"Duplicate JSON key: {key}")
            value[key] = item
        return value

    def invalid_constant(value):
        raise ValueError(f"Non-finite JSON constant: {value}")

    payload = json.loads(path.read_text(encoding="utf-8-sig"), parse_float=Decimal,
                         parse_int=Decimal, parse_constant=invalid_constant,
                         object_pairs_hook=no_duplicates)
    expected = {"schema_version", "source", "start_ms", "end_ms", "duration_ms", "words", "phones"}
    if not isinstance(payload, dict) or set(payload) != expected or payload["schema_version"] != "0.1":
        raise ValueError("Expected the exact TASK-002 alignment schema 0.1")
    intervals = {}
    for name, model in (("words", WordInterval), ("phones", PhoneInterval)):
        if not isinstance(payload[name], list):
            raise ValueError("Alignment intervals must be JSON arrays")
        items = []
        keys = {"label", "start_ms", "end_ms"} | ({"duration_ms"} if name == "phones" else set())
        for item in payload[name]:
            if not isinstance(item, dict) or set(item) != keys:
                raise ValueError(f"Invalid {name} interval schema")
            items.append(model(item["label"], item["start_ms"], item["end_ms"]))
        intervals[name] = tuple(items)
    result = AlignmentResult(payload["source"], payload["start_ms"], payload["end_ms"],
                             intervals["words"], intervals["phones"])
    validate_alignment(result)
    if not isinstance(payload["duration_ms"], Decimal) or payload["duration_ms"] != result.duration_ms:
        raise ValueError("Alignment duration does not match source boundaries")
    for raw, phone in zip(payload["phones"], result.phones):
        if not isinstance(raw["duration_ms"], Decimal) or raw["duration_ms"] != phone.duration_ms:
            raise ValueError("Phone duration does not match source boundaries")
    return result
