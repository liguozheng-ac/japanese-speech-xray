"""Post-analysis measurements; only this layer joins ground truth to estimates."""
from collections import Counter
from decimal import Decimal
from fractions import Fraction
import numpy as np
from speech_xray.reference.numeric import decimal_ratio
from speech_xray.deviation.duration import FEATURES
from . import FACTORS


def recovery(ground_truth, result):
    span = result['estimated_span']
    if span is None or ground_truth is None:
        return None
    rate = int(ground_truth['sample_rate_hz'])
    known = Fraction(int(ground_truth['actual_perturbed_duration_samples']) * 1000, rate)
    recovered = Fraction(span['end_ms']) - Fraction(span['start_ms'])
    error = recovered - known
    return {'known_duration_ms': decimal_ratio(known), 'recovered_duration_ms': decimal_ratio(recovered),
        'signed_error_ms': decimal_ratio(error), 'absolute_error_ms': decimal_ratio(abs(error)),
        'relative_error': decimal_ratio(error / known),
        'start_error_ms': decimal_ratio(Fraction(span['start_ms']) - Fraction(int(ground_truth['perturbed_target_sample_start']) * 1000, rate)),
        'end_error_ms': decimal_ratio(Fraction(span['end_ms']) - Fraction(int(ground_truth['perturbed_target_sample_end']) * 1000, rate)),
        'meaning': 'MFA_RECOVERY_OF_DEFINED_MANIPULATION_REGION_NOT_PHONETIC_GOLD_BOUNDARIES'}


def f0_region(acoustic, start, end):
    track = acoustic.get('track')
    if not track:
        return {'selected_frames': 0, 'voiced_frames': 0, 'median_f0_hz': None, 'status': 'NO_TRACK'}
    selected = [frame for frame in track['frames'] if start <= frame['center_sample'] < end]
    voiced = [float(frame['f0_hz']) for frame in selected if frame['voiced'] is True and frame['f0_hz'] is not None]
    return {'selected_frames': len(selected), 'voiced_frames': len(voiced),
        'median_f0_hz': float(np.median(voiced)) if voiced else None,
        'status': 'AVAILABLE' if voiced else 'NO_VOICED_FRAMES',
        'selection': 'FRAME_CENTERS_IN_MANIPULATION_SAMPLE_DOMAIN',
        'full_window_can_include_transition_context': True}


def control_semantics(base, result, accepted_acoustic, actual_acoustic):
    target = base['accepted_original_span']
    estimate = result['estimated_span']
    original = next(span for span in accepted_acoustic['span_evidence'] if span['span_id'] == target['id'])
    actual = result.get('target_acoustics')
    return {'reanalysed_from_wav': result['checks']['mfa_completed'],
        'target_timing_and_identity_exact': estimate == target,
        'target_acoustic_semantics_exact': actual == original,
        'whole_utterance_acoustic_track_exact': accepted_acoustic['track'] == actual_acoustic.get('track'),
        'full_pipeline_available': result['checks']['deviation_evidence_available']}


METRICS = ('raw_duration_ms', 'rate_normalized_duration', 'signed_delta', 'ratio_to_median', 'mad_distance')


def value(row, metric):
    pipeline = row['pipeline']
    if not pipeline['checks']['deviation_evidence_available']:
        return None
    if metric in ('raw_duration_ms', 'rate_normalized_duration'):
        return pipeline['duration'][metric]
    return pipeline['deviation']['features']['rate_normalized_duration'][metric]


def monotonicity(rows):
    bases = sorted({row['base_id'] for row in rows})
    output = {}
    for metric in METRICS:
        reversals, equal, monotonic, unavailable = [], 0, 0, 0
        for base in bases:
            ordered = sorted((row for row in rows if row['base_id'] == base), key=lambda row: Fraction(row['factor']))
            for left, right in zip(ordered, ordered[1:]):
                first, last = value(left, metric), value(right, metric)
                if first is None or last is None:
                    unavailable += 1
                elif last >= first:
                    monotonic += 1; equal += int(last == first)
                else:
                    reversals.append({'base_id': base, 'left_case_id': left['case_id'], 'right_case_id': right['case_id'],
                        'left_factor': left['factor'], 'right_factor': right['factor'], 'left_value': first, 'right_value': last,
                        'left_estimated_span': left['pipeline']['estimated_span'], 'right_estimated_span': right['pipeline']['estimated_span'],
                        'left_rate_context': left['pipeline']['rate_context'], 'right_rate_context': right['pipeline']['rate_context']})
        comparable = monotonic + len(reversals)
        output[metric] = {'adjacent_factor_pairs': monotonic + len(reversals) + unavailable,
            'comparable_pairs': comparable, 'monotonic_pairs': monotonic, 'equal_pairs': equal,
            'non_monotonic_pairs': len(reversals), 'unavailable_pairs': unavailable,
            'monotonic_pair_proportion': decimal_ratio(Fraction(monotonic, comparable)) if comparable else None,
            'reversals': reversals, 'criterion': 'NONDECREASING_AS_DURATION_FACTOR_INCREASES'}
    return output


def stats(values):
    values = [Fraction(value) for value in values if value is not None]
    if not values: return {'count': 0, 'minimum': None, 'median': None, 'maximum': None, 'mean': None}
    values.sort(); n = len(values)
    median = values[n//2] if n % 2 else (values[n//2-1] + values[n//2]) / 2
    return {'count': n, 'minimum': decimal_ratio(values[0]), 'median': decimal_ratio(median),
        'maximum': decimal_ratio(values[-1]), 'mean': decimal_ratio(sum(values) / n)}


def aggregate(rows):
    names = {'successful_alignment': 'mfa_completed', 'valid_textgrids': 'textgrid_valid', 'successful_mapping': 'long_vowel_mapping_valid',
        'successful_acoustics': 'acoustic_evidence_available', 'successful_normalization': 'normalized_duration_available',
        'successful_deviation': 'deviation_evidence_available'}
    counts = {key: sum(row['pipeline']['checks'][check] for row in rows) for key, check in names.items()}
    failures = Counter(category for row in rows for category in row['pipeline']['failure_categories'])
    errors = [row['recovery'] for row in rows if row['recovery'] is not None]
    manipulated = [row for row in rows if row['ground_truth'] is not None]
    return {'case_count': len(rows), **counts, 'abstentions': sum(row['pipeline']['final_status'] != 'EVIDENCE_AVAILABLE' for row in rows),
        'failure_categories': dict(sorted(failures.items())),
        'duration_recovery_error': {key: stats(error[key] for error in errors) for key in
            ('signed_error_ms', 'absolute_error_ms', 'relative_error', 'start_error_ms', 'end_error_ms')},
        'f0_available_after': sum(row['pitch']['after']['median_f0_hz'] is not None for row in rows),
        'f0_change_hz_within_base_only': stats(row['pitch']['median_f0_delta_hz'] for row in rows),
        'local_safety_attenuation_cases': sum(any(gain < 1 for gain in row['ground_truth']['normalization']['local_pre_crossfade_safety_gains']) for row in manipulated),
        'target_rms_ratio': stats(Fraction(str(row['ground_truth']['artifacts']['target_rms_after'])) /
            Fraction(str(row['ground_truth']['artifacts']['target_rms_before'])) for row in manipulated
            if row['ground_truth']['artifacts']['target_rms_before'] > 0)}


def summarize(rows, expected_case_ids):
    if len({row['case_id'] for row in rows}) != len(rows) or set(expected_case_ids) != {row['case_id'] for row in rows}:
        raise ValueError('NO_CASE_MAY_BE_DROPPED_OR_DUPLICATED')
    by_factor = {factor: aggregate([row for row in rows if row['factor'] == factor]) for factor in FACTORS}
    by_target = {target: {**aggregate([row for row in rows if row['target_id'] == target]),
        'monotonicity': monotonicity([row for row in rows if row['target_id'] == target])}
        for target in sorted({row['target_id'] for row in rows})}
    # These are the two smallest predeclared engineering factors, not a pronunciation cutoff.
    low = [row for row in rows if row['factor'] in FACTORS[:2]]
    control = [row for row in rows if row['factor'] == '1.00']
    low_failed = sum(not row['pipeline']['checks']['deviation_evidence_available'] for row in low)
    control_failed = sum(not row['pipeline']['checks']['deviation_evidence_available'] for row in control)
    low_rate = Fraction(low_failed, len(low)) if low else None
    control_rate = Fraction(control_failed, len(control)) if control else None
    low_state = (True if low_failed == 0 else False if low_failed == len(low) else 'partial') if low else 'partial'
    bias = low_rate > control_rate if low_rate is not None and control_rate is not None else 'inconclusive'
    representatives = {}
    for row in rows:
        for category in row['pipeline']['failure_categories']:
            representatives.setdefault(category, []).append(row['case_id'])
    return {'schema_version': '0.1', 'representation': 'CONTROLLED_PIPELINE_STRESS_SUMMARY',
        'overall': aggregate(rows), 'by_target': by_target, 'by_factor': by_factor,
        'monotonicity': monotonicity(rows), 'failure_representatives': {key: ids[:3] for key, ids in sorted(representatives.items())},
        'all_failure_case_ids': representatives,
        'success_only_bias': {'assessment': bias, 'predeclared_low_factors': list(FACTORS[:2]),
            'low_factor_cases': len(low), 'low_factor_failures': low_failed, 'control_cases': len(control),
            'control_failures': control_failed, 'low_factor_failure_proportion': decimal_ratio(low_rate) if low_rate is not None else None,
            'control_failure_proportion': decimal_ratio(control_rate) if control_rate is not None else None,
            'criterion': 'OBSERVED_LOW_FACTOR_EVIDENCE_FAILURE_PROPORTION_EXCEEDS_CONTROL_NO_INFERENTIAL_CLAIM'},
        'gates': {'CONTROLLED_PERTURBATION_ENGINE_READY': bool(rows) and all(row['ground_truth'] is not None and all(
            v for v in row['ground_truth']['integrity'].values() if v is not None) for row in rows), 'PIPELINE_STRESS_BENCHMARK_COMPLETE': True,
            'SEVERE_SHORTENING_ANALYZABLE': low_state, 'POTENTIAL_SUCCESS_ONLY_BIAS': bias,
            'REAL_LABELLED_LEARNER_DATA_READY': False},
        'interpretation': 'ENGINEERING_RESPONSE_TO_CONTROLLED_DURATION_MANIPULATION_NOT_LEARNER_PRONUNCIATION_DIAGNOSIS'}
