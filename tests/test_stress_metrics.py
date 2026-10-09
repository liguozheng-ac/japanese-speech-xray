"""Authored recovery mathematics and failure-denominator contracts."""
from copy import deepcopy
from decimal import Decimal as D
from pathlib import Path
import tempfile
import unittest
from reference_test_support import ROOT
from speech_xray.stress import FACTORS
from speech_xray.stress.metrics import recovery, monotonicity, summarize, f0_region
from speech_xray.stress.artifacts import ROOT as PRIVATE_ROOT, save, load
from speech_xray.stress.runner import manipulation_failure


def rows():
    output = []
    for factor in FACTORS:
        x = D(factor)
        output.append({'case_id': 'authored-' + factor, 'base_id': 'authored', 'target_id': 'authored-target', 'factor': factor,
            'ground_truth': {'integrity': {'ok': True}, 'normalization': {'local_pre_crossfade_safety_gains': [1]},
                'artifacts': {'target_rms_before': .1, 'target_rms_after': .1}},
            'pipeline': {'checks': {key: True for key in ('mfa_completed', 'textgrid_valid', 'long_vowel_mapping_valid',
                'acoustic_evidence_available', 'normalized_duration_available', 'deviation_evidence_available')},
                'final_status': 'EVIDENCE_AVAILABLE', 'failure_categories': [], 'estimated_span': None, 'rate_context': None,
                'duration': {'raw_duration_ms': 100 * x, 'rate_normalized_duration': x},
                'deviation': {'features': {'rate_normalized_duration': {'signed_delta': x - 1, 'ratio_to_median': x, 'mad_distance': x - 1}}}},
            'recovery': None, 'pitch': {'after': {'median_f0_hz': 180}, 'median_f0_delta_hz': 0}})
    return output


class MetricTests(unittest.TestCase):
    def test_exact_duration_recovery_error_independent_of_aligner(self):
        gt = {'sample_rate_hz': 24000, 'actual_perturbed_duration_samples': 720,
            'perturbed_target_sample_start': 2400, 'perturbed_target_sample_end': 3120}
        result = {'estimated_span': {'start_ms': D(110), 'end_ms': D(150)}}
        answer = recovery(gt, result)
        self.assertEqual(answer['known_duration_ms'], D(30));self.assertEqual(answer['signed_error_ms'], D(10))
        self.assertEqual(answer['start_error_ms'], D(10));self.assertEqual(answer['end_error_ms'], D(20))

    def test_missing_recovery_is_null(self):
        self.assertIsNone(recovery({}, {'estimated_span': None}))
        self.assertIsNone(recovery(None, {'estimated_span': {'start_ms': D(1), 'end_ms': D(2)}}))

    def test_all_adjacent_pairs_accounted_for(self):
        result = monotonicity(rows())
        for metric in result.values():
            self.assertEqual(metric['adjacent_factor_pairs'], 11)
            self.assertEqual(metric['monotonic_pairs'], 11)
            self.assertEqual(metric['non_monotonic_pairs'], 0)

    def test_reversal_retains_values_and_locations(self):
        data = rows();data[1]['pipeline']['duration']['raw_duration_ms'] = D(1)
        result = monotonicity(data)['raw_duration_ms']
        self.assertEqual(result['non_monotonic_pairs'], 1)
        self.assertEqual(result['reversals'][0]['left_factor'], '0.20')
        self.assertEqual(result['reversals'][0]['right_factor'], '0.30')

    def test_missing_evidence_pair_not_assumed_monotonic(self):
        data = rows();data[1]['pipeline']['checks']['deviation_evidence_available'] = False
        result = monotonicity(data)['raw_duration_ms']
        self.assertEqual(result['unavailable_pairs'], 2);self.assertEqual(result['comparable_pairs'], 9)

    def test_failure_counts_remain_in_factor_denominator(self):
        data = rows();data[0]['pipeline']['checks']['deviation_evidence_available'] = False
        data[0]['pipeline']['final_status'] = 'ABSTAIN';data[0]['pipeline']['failure_categories'] = ['MORA_MAPPING_FAILURE']
        result = summarize(data, [row['case_id'] for row in data])
        self.assertEqual(result['by_factor']['0.20']['case_count'], 1)
        self.assertEqual(result['overall']['abstentions'], 1)
        self.assertEqual(result['gates']['SEVERE_SHORTENING_ANALYZABLE'], 'partial')
        self.assertIs(result['gates']['POTENTIAL_SUCCESS_ONLY_BIAS'], True)
        self.assertEqual(result['failure_representatives']['MORA_MAPPING_FAILURE'], ['authored-0.20'])

    def test_no_observed_failure_differential(self):
        data = rows();result = summarize(data, [row['case_id'] for row in data])
        self.assertIs(result['gates']['POTENTIAL_SUCCESS_ONLY_BIAS'], False)
        self.assertIs(result['gates']['SEVERE_SHORTENING_ANALYZABLE'], True)
        self.assertIs(result['gates']['REAL_LABELLED_LEARNER_DATA_READY'], False)

    def test_duplicate_or_dropped_case_rejected(self):
        data = rows();expected = [row['case_id'] for row in data]
        with self.assertRaises(ValueError): summarize(data[:-1], expected)
        with self.assertRaises(ValueError): summarize(data + [data[0]], expected)

    def test_f0_selects_ground_truth_frame_centers_only(self):
        acoustic = {'track': {'frames': [{'center_sample': i, 'voiced': True, 'f0_hz': 180} for i in (99, 100, 199, 200)]}}
        result = f0_region(acoustic, 100, 200)
        self.assertEqual(result['selected_frames'], 2);self.assertEqual(result['median_f0_hz'], 180)
        self.assertTrue(result['full_window_can_include_transition_context'])

    def test_no_voiced_frames_explicit(self):
        result = f0_region({'track': {'frames': [{'center_sample': 150, 'voiced': False, 'f0_hz': None}]}}, 100, 200)
        self.assertEqual(result['status'], 'NO_VOICED_FRAMES');self.assertIsNone(result['median_f0_hz'])

    def test_private_serialization_round_trip_and_no_overwrite(self):
        PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT, prefix='authored-unit-') as directory:
            path = Path(directory)/'fixture.json';save(path, {'value': D('.2'), 'material_kind': 'AUTHORED_WAVEFORM_FIXTURE'})
            self.assertEqual(load(path)['value'], D('.2'))
            with self.assertRaises(ValueError): save(path, {'value': D('.3')})
        with self.assertRaises(ValueError): save(ROOT/'public-forbidden.json', {})

    def test_manipulation_failure_is_retained_with_no_fabricated_truth(self):
        PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT, prefix='authored-unit-') as directory:
            base = {'base_id': 'authored', 'target': {'target_id': 'authored-target'}, 'speaker_id': 'authored-speaker'}
            row = manipulation_failure(base, '0.20', ValueError('AUTHORED_FAILURE'), directory)
            self.assertIsNone(row['ground_truth']);self.assertEqual(row['pipeline']['failure_categories'], ['MANIPULATION_FAILURE'])

    def test_low_factors_all_fail_returns_false(self):
        data = rows()
        for row in data[:2]:
            row['pipeline']['checks']['deviation_evidence_available'] = False;row['pipeline']['final_status'] = 'ABSTAIN'
        result = summarize(data, [row['case_id'] for row in data])
        self.assertIs(result['gates']['SEVERE_SHORTENING_ANALYZABLE'], False)

    def test_zero_mad_distance_null_pairs_explicit(self):
        data = rows()
        for row in data: row['pipeline']['deviation']['features']['rate_normalized_duration']['mad_distance'] = None
        self.assertEqual(monotonicity(data)['mad_distance']['unavailable_pairs'], 11)
