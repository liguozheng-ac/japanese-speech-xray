"""Read Praat long/short text TextGrids, without importing aligner internals."""

from decimal import Decimal
from pathlib import Path
import re

from .models import AlignmentResult, PhoneInterval, WordInterval, milliseconds


class TextGridParseError(ValueError):
    """The input is malformed, unsupported, or has ambiguous evidence tiers."""


_TOKEN = re.compile(r'"(?:[^"\x00]|"")*"|<exists>|[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?')
_ANNOTATION = re.compile(r'(?:item\s*\[\s*\d*\s*\]|intervals\s*\[\s*\d+\s*\]|points\s*\[\s*\d+\s*\])\s*:')
_ASSIGNMENT = re.compile(r'(?:File type|Object class|xmin|xmax|size|class|name|text|number|mark|intervals:\s*size|points:\s*size)\s*=')


def _tokens(text: str) -> list[str]:
    # Praat annotations are descriptive; the ordered values carry the structure.
    values = []
    offset = 0
    while offset < len(text):
        whitespace = re.match(r'\s+', text[offset:])
        if whitespace:
            offset += whitespace.end()
            continue
        for pattern in (_ANNOTATION, _ASSIGNMENT):
            match = pattern.match(text, offset)
            if match:
                offset = match.end()
                break
        else:
            tier_flag = re.match(r'tiers\?\s*', text[offset:])
            if tier_flag:
                offset += tier_flag.end()
                continue
            token = _TOKEN.match(text, offset)
            if not token:
                raise TextGridParseError(f"Unexpected text at character {offset}")
            values.append(token.group())
            offset = token.end()
    return values


def parse_textgrid(path: str | Path) -> AlignmentResult:
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8-sig")
    except UnicodeError as error:
        raise TextGridParseError("Expected UTF-8 text TextGrid (binary formats unsupported)") from error
    tokens = _tokens(text)
    cursor = 0

    def take() -> str:
        nonlocal cursor
        if cursor >= len(tokens):
            raise TextGridParseError("Truncated TextGrid")
        value = tokens[cursor]
        cursor += 1
        return value

    def string() -> str:
        value = take()
        if not value.startswith('"'):
            raise TextGridParseError("Expected a quoted string")
        return value[1:-1].replace('""', '"')

    def number() -> Decimal:
        value = take()
        if value.startswith('"') or value == '<exists>':
            raise TextGridParseError("Expected a finite numeric boundary")
        return Decimal(value)

    def count() -> int:
        value = number()
        if value < 0 or value != value.to_integral_value():
            raise TextGridParseError("Expected a non-negative integer count")
        return int(value)

    def bounds(start, end, lower, upper):
        if start < lower or end > upper or end < start:
            raise TextGridParseError("Invalid or out-of-range interval boundaries")

    if string() not in {"ooTextFile", "ooTextFile short"} or string() != "TextGrid":
        raise TextGridParseError("Unsupported TextGrid header")
    start, end = number(), number()
    if start < 0 or end < start:
        raise TextGridParseError("Invalid TextGrid time domain")
    if take() != '<exists>':
        raise TextGridParseError("Expected tiers <exists>")
    tiers: dict[str, list] = {}
    names = set()
    for _ in range(count()):
        kind, name = string(), string()
        lower, upper = number(), number()
        bounds(lower, upper, start, end)
        items = []
        previous = lower
        for _ in range(count()):
            if kind == "IntervalTier":
                left, right, label = number(), number(), string()
                bounds(left, right, lower, upper)
                if left < previous:
                    raise TextGridParseError("Overlapping or unordered intervals")
                previous = right
                items.append((label, milliseconds(left), milliseconds(right)))
            elif kind == "TextTier":
                position = number()
                string()
                bounds(position, position, lower, upper)
                if position < previous:
                    raise TextGridParseError("Unordered points")
                previous = position
            else:
                raise TextGridParseError(f"Unsupported tier class: {kind}")
        if kind not in {"IntervalTier", "TextTier"}:
            raise TextGridParseError(f"Unsupported tier class: {kind}")
        if name in names:
            raise TextGridParseError(f"Duplicate tier name: {name}")
        names.add(name)
        if kind == "IntervalTier":
            tiers[name] = items
    if cursor != len(tokens):
        raise TextGridParseError("Unexpected trailing TextGrid values")

    def select(suffix):
        matches = [items for name, items in tiers.items()
                   if name.casefold() == suffix or name.casefold().endswith(" - " + suffix)]
        if len(matches) != 1:
            raise TextGridParseError(f"Expected exactly one {suffix} interval tier, found {len(matches)}")
        return matches[0]

    # Preserve empty labels, explicit silence labels and zero-duration intervals.
    return AlignmentResult(source.name, milliseconds(start), milliseconds(end),
                           tuple(WordInterval(*item) for item in select("words")),
                           tuple(PhoneInterval(*item) for item in select("phones")))
