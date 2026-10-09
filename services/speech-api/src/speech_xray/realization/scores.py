"""Explicit score comparability gates, without hypothesis decisions from deltas."""
from decimal import Decimal


def compare_scores(scores):
    """Unknown feature identity or normalization never implies comparability."""
    required = ('audio_sha256', 'model_sha256', 'configuration_sha256', 'mfa_version',
                'feature_sha256', 'normalization', 'frame_basis', 'num_frames',
                'adaptation', 'score_semantics')
    if len(scores) != 3:
        return {'comparable': 'inconclusive', 'reasons': ['THREE_CONDITION_SCORES_REQUIRED'], 'usage': 'DESCRIPTIVE_ONLY'}
    rows = list(scores.values())
    if any(row.get('condition_specific_transform') is True for row in rows):
        return {'comparable': False, 'reasons': ['CONDITION_SPECIFIC_ADAPTATION'], 'usage': 'DESCRIPTIVE_ONLY'}
    reasons = []
    unknown = False
    for field in required:
        values = [r.get(field) for r in rows]
        if any(v is None for v in values): unknown = True; reasons.append('MISSING_' + field.upper())
        elif any(v != values[0] for v in values[1:]): reasons.append('DIFFERENT_' + field.upper())
    for row in rows:
        value = row.get('alignment_log_likelihood')
        if value is None: unknown = True; reasons.append('ALIGNMENT_SCORE_UNAVAILABLE')
        elif not Decimal(str(value)).is_finite(): raise ValueError('INVALID_EXPERIMENT_INPUT: nonfinite score')
    result = False if any(r.startswith('DIFFERENT_') for r in reasons) else 'inconclusive' if unknown else True
    return {'comparable': result, 'reasons': sorted(set(reasons)),
            'usage': 'AUXILIARY_ENGINEERING_DESCRIPTION_NO_VARIANT_DECISION' if result is True else 'DESCRIPTIVE_ONLY'}
