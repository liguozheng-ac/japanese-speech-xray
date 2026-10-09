"""Dimensionless duration features; no correctness target or learner comparison."""

from fractions import Fraction

from speech_xray.japanese.models import LongVowelSpan
from .models import NormalizedDuration, RateContext
from .numeric import decimal_ratio


def normalize_duration(span: LongVowelSpan, rate: RateContext) -> NormalizedDuration:
    raw = span.duration_ms
    if raw <= 0 or rate.mora_count <= 0 or rate.core_speech_duration_ms <= 0:
        raise ValueError("Normalization requires positive durations and mora count")
    # Use the exact underlying ratio, not the rounded display of mean period.
    feature = Fraction(raw) * rate.mora_count / Fraction(rate.core_speech_duration_ms)
    return NormalizedDuration(raw, decimal_ratio(feature), decimal_ratio(feature / span.mora_span))
