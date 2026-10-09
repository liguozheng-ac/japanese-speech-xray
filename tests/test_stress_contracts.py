"""Public contracts with no corpus identities or observed private values."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from reference_test_support import ROOT
from speech_xray.stress.artifacts import ROOT as PRIVATE_ROOT, save, pin
from speech_xray.stress.runner import align_group


class StressSchemaTests(unittest.TestCase):
    def test_ground_truth_is_separate_from_pipeline_schema(self):
        folder = ROOT/'data/benchmarks'
        gt = json.loads((folder/'duration-manipulation.schema.json').read_text())
        pipeline = json.loads((folder/'stress-pipeline-result.schema.json').read_text())
        self.assertEqual(gt['properties']['representation']['const'], 'MANIPULATION_GROUND_TRUTH')
        self.assertEqual(pipeline['properties']['representation']['const'], 'MFA_ESTIMATED_ALIGNMENT_PIPELINE_RESULT')
        self.assertNotIn('ground_truth', pipeline['properties'])
        self.assertNotIn('estimated_span', gt['properties'])
        self.assertTrue(set(gt['required']) <= set(gt['properties']))

    def test_gates_keep_learner_readiness_false(self):
        schema = json.loads((ROOT/'data/benchmarks/stress-summary.schema.json').read_text())
        gates = schema['properties']['gates']['properties']
        self.assertEqual(gates['REAL_LABELLED_LEARNER_DATA_READY'], {'const': False})
        self.assertEqual(gates['SEVERE_SHORTENING_ANALYZABLE']['enum'], [True, False, 'partial'])
        self.assertEqual(gates['POTENTIAL_SUCCESS_ONLY_BIAS']['enum'], [True, False, 'inconclusive'])

    def test_generic_schemas_have_no_private_identity(self):
        for path in (ROOT/'data/benchmarks').glob('*.json'):
            text = path.read_text()
            self.assertNotIn('jvs001', text);self.assertNotIn('VOICEACTRESS100', text)
            self.assertNotIn('D:', text)


class MfaCacheContractTests(unittest.TestCase):
    def test_mfa_failure_is_recorded_and_not_dropped(self):
        PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT, prefix='authored-unit-') as directory:
            root = Path(directory);audio=root/'authored-audio.ref';lab=root/'authored.lab'
            audio.write_bytes(b'AUTHORED_ENGINEERING_INPUT_IDENTITY');lab.write_bytes(b'AUTHORED_TRANSCRIPT\n')
            inputs = [{'stem': 'authored-one-speaker', 'audio': pin(audio), 'transcript': pin(lab)}]
            with patch('speech_xray.stress.runner.mfa_align', side_effect=ValueError('AUTHORED_MFA_FAILURE')) as aligner:
                result = align_group(inputs, root/'attempt')
                reused = align_group(inputs, root/'attempt')
            self.assertFalse(result['mfa_process_completed']);self.assertEqual(result['utterance_count'], 1)
            self.assertEqual(result['failure']['reason'], 'AUTHORED_MFA_FAILURE')
            self.assertTrue(reused['execution_cache_hit']);self.assertEqual(aligner.call_count, 1)

    def test_corrupted_cached_input_rejected(self):
        PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT, prefix='authored-unit-') as directory:
            root = Path(directory);audio=root/'authored-audio.ref';lab=root/'authored.lab'
            audio.write_bytes(b'AUTHORED');lab.write_bytes(b'KNOWN\n')
            inputs = [{'stem': 'authored-one-speaker', 'audio': pin(audio), 'transcript': pin(lab)}]
            with patch('speech_xray.stress.runner.mfa_align', side_effect=ValueError('AUTHORED_MFA_FAILURE')):
                align_group(inputs, root/'attempt')
            (root/'attempt/input/authored-one-speaker.lab').write_bytes(b'CHANGED\n')
            with self.assertRaises(ValueError): align_group(inputs, root/'attempt')

    def test_incomplete_attempt_preserved(self):
        PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT, prefix='authored-unit-') as directory:
            root = Path(directory);(root/'attempt').mkdir()
            with self.assertRaises(ValueError): align_group([], root/'attempt')
