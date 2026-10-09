"""MFA-independent alignment evidence, measured in decimal milliseconds."""

from dataclasses import dataclass
from decimal import Decimal, localcontext
import json


def exact_subtract(left: Decimal, right: Decimal) -> Decimal:
    """Avoid rounding even when source boundaries exceed Decimal's default precision."""
    low = min(left.as_tuple().exponent, right.as_tuple().exponent)
    high = max(left.adjusted(), right.adjusted(), 0)
    with localcontext() as context:
        context.prec = max(28, high - low + 3)
        return left - right


def milliseconds(seconds: Decimal) -> Decimal:
    parts = seconds.as_tuple()
    return Decimal((parts.sign, parts.digits, parts.exponent + 3))


@dataclass(frozen=True)
class WordInterval:
    label: str
    start_ms: Decimal
    end_ms: Decimal

    def to_dict(self) -> dict:
        return {"label": self.label, "start_ms": self.start_ms, "end_ms": self.end_ms}


@dataclass(frozen=True)
class PhoneInterval(WordInterval):
    @property
    def duration_ms(self) -> Decimal:
        return exact_subtract(self.end_ms, self.start_ms)

    def to_dict(self) -> dict:
        return {**super().to_dict(), "duration_ms": self.duration_ms}


@dataclass(frozen=True)
class AlignmentResult:
    source: str
    start_ms: Decimal
    end_ms: Decimal
    words: tuple[WordInterval, ...]
    phones: tuple[PhoneInterval, ...]

    @property
    def duration_ms(self) -> Decimal:
        return exact_subtract(self.end_ms, self.start_ms)

    def to_dict(self) -> dict:
        return {
            "schema_version": "0.1", "source": self.source,
            "start_ms": self.start_ms, "end_ms": self.end_ms,
            "duration_ms": self.duration_ms,
            "words": [item.to_dict() for item in self.words],
            "phones": [item.to_dict() for item in self.phones],
        }

    def to_json(self) -> str:
        """Serialize Decimal as JSON numbers without a binary float round trip."""
        def encode(value):
            if isinstance(value, Decimal):
                if not value.is_finite():
                    raise ValueError("Non-finite alignment boundary")
                return str(value)
            if isinstance(value, dict):
                return "{" + ", ".join(json.dumps(k) + ": " + encode(v) for k, v in value.items()) + "}"
            if isinstance(value, list):
                return "[" + ", ".join(encode(v) for v in value) + "]"
            return json.dumps(value, ensure_ascii=False, allow_nan=False)
        return encode(self.to_dict()) + "\n"
