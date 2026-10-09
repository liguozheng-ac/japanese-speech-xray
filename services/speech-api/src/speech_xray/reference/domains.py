"""Exact, positive interval containment in the original audio sample domain."""

from decimal import Decimal
from fractions import Fraction


def interval_inside_audio(start_ms, end_ms, frame_count, sample_rate):
    """No display rounding, padding allowance, frame-hop or millisecond tolerance."""
    if (not isinstance(start_ms, Decimal) or not start_ms.is_finite()
            or not isinstance(end_ms, Decimal) or not end_ms.is_finite()
            or type(frame_count) is not int or type(sample_rate) is not int
            or frame_count <= 0 or sample_rate <= 0):
        return False
    return 0 <= Fraction(start_ms) < Fraction(end_ms) <= Fraction(frame_count * 1000, sample_rate)
