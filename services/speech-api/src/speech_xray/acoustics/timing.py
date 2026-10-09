"""Exact coordinate decisions; derived rational times display at 34 digits."""

from decimal import Decimal, localcontext
from fractions import Fraction


def sample_time_ms(sample: int, sample_rate: int) -> Decimal:
    with localcontext() as context:
        context.prec = 34
        return Decimal(sample * 1000) / Decimal(sample_rate)


def time_fraction_ms(value: Decimal) -> Fraction:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("Alignment time must be finite Decimal")
    return Fraction(value)


def quantize_interval(start: Decimal, end: Decimal, sample_rate: int) -> tuple[int, int]:
    left = time_fraction_ms(start) * sample_rate / 1000
    right = time_fraction_ms(end) * sample_rate / 1000
    if right < left:
        raise ValueError("Reversed interval")
    first = left.numerator // left.denominator
    last = first if right == left else -(-right.numerator // right.denominator)
    return first, last


def center_in_span(center_sample: int, sample_rate: int, start: Decimal, end: Decimal) -> bool:
    center = Fraction(center_sample * 1000, sample_rate)
    return time_fraction_ms(start) <= center < time_fraction_ms(end)
