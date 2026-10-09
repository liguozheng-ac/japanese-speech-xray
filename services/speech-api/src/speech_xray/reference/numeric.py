"""Exact ratios for calculations; source Decimal boundaries are never rounded."""

from decimal import Decimal, localcontext
from fractions import Fraction

DERIVED_PRECISION = 50


def decimal_ratio(value: Fraction) -> Decimal:
    with localcontext() as context:
        context.prec = DERIVED_PRECISION
        return Decimal(value.numerator) / Decimal(value.denominator)


def finite_decimal(value, name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite JSON number")
    return value


def integer(value, name: str) -> int:
    value = finite_decimal(value, name)
    if value < 0 or value > 2**63 - 1 or value != value.to_integral_value():
        raise ValueError(f"{name} must be a nonnegative 64-bit integer")
    return int(value)
