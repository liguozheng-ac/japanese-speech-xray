"""Unscaled MAD and linear quantiles on retained speaker observations."""

from decimal import Decimal
from fractions import Fraction

from .models import RobustStatistics
from .numeric import decimal_ratio


def _quantile(values, fraction):
    position = (len(values) - 1) * fraction
    low = position.numerator // position.denominator
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def summarize(values) -> RobustStatistics:
    source = tuple(values)
    if not source:
        return RobustStatistics()
    if any(not isinstance(value, Decimal) or not value.is_finite() for value in source):
        raise ValueError("Statistics require finite Decimal observations")
    ordered = sorted(Fraction(value) for value in source)
    median = _quantile(ordered, Fraction(1, 2))
    mad = _quantile(sorted(abs(value - median) for value in ordered), Fraction(1, 2))
    q25, q75 = _quantile(ordered, Fraction(1, 4)), _quantile(ordered, Fraction(3, 4))
    return RobustStatistics(len(source), *(decimal_ratio(value) for value in
                            (median, mad, q25, q75, q75 - q25, ordered[0], ordered[-1])),
                            "ZERO_MAD" if mad == 0 else "NONZERO_MAD")
