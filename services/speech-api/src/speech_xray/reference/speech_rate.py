"""Transparent utterance mora rate includes internal pauses in the core interval."""

from fractions import Fraction

from speech_xray.alignment.models import AlignmentResult, exact_subtract
from .models import RateContext
from .numeric import decimal_ratio


def measure_utterance_rate(alignment: AlignmentResult, mora_count: int) -> RateContext:
    words = [word for word in alignment.words if word.label.strip()]
    if not words or type(mora_count) is not int or mora_count <= 0:
        raise ValueError("Rate requires nonempty words and positive valid mora count")
    start, end = words[0].start_ms, words[-1].end_ms
    duration = exact_subtract(end, start)
    if duration <= 0:
        raise ValueError("Core speech duration must be positive")
    return RateContext(start, end, duration, mora_count,
                       decimal_ratio(Fraction(mora_count * 1000) / Fraction(duration)),
                       decimal_ratio(Fraction(duration) / mora_count))
