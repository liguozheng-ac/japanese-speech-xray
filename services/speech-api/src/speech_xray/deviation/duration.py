"""Continuous descriptive formulas, with no thresholds or scale substitution."""
from fractions import Fraction
from speech_xray.reference.numeric import finite_decimal, decimal_ratio

FEATURES = ('raw_duration_ms', 'rate_normalized_duration', 'rate_normalized_duration_per_mora')
FORMULAS = {'signed_delta':'x - median', 'ratio_to_median':'x / median',
            'mad_distance':'(x - median) / unscaled_MAD when MAD > 0',
            'inside_iqr':'q25 <= x <= q75', 'inside_observed_min_max':'min <= x <= max'}


def describe_duration(value, statistics):
    x = Fraction(finite_decimal(value, 'candidate value'))
    m = Fraction(finite_decimal(statistics.median, 'median'))
    d = Fraction(finite_decimal(statistics.mad, 'MAD'))
    if x <= 0 or m <= 0 or d < 0:
        raise ValueError('POSITIVE_DURATION_AND_MEDIAN_NONNEGATIVE_MAD_REQUIRED')
    delta = x - m
    return {'candidate_value':value, 'signed_delta':decimal_ratio(delta),
            'ratio_to_median':decimal_ratio(x / m),
            'mad_distance':decimal_ratio(delta / d) if d else None,
            'mad_distance_status':'DEFINED' if d else 'ZERO_MAD',
            'direction':('BELOW_REFERENCE_MEDIAN' if delta < 0 else
                         'ABOVE_REFERENCE_MEDIAN' if delta > 0 else 'AT_REFERENCE_MEDIAN'),
            'inside_iqr':Fraction(statistics.q25) <= x <= Fraction(statistics.q75),
            'inside_observed_min_max':Fraction(statistics.minimum) <= x <= Fraction(statistics.maximum)}
