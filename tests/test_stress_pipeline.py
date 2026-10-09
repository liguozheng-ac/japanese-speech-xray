"""Authored structural bundles; these tests do not assert real MFA recovery."""
from pathlib import Path
import inspect
import tempfile
import unittest
from unittest.mock import patch
from reference_test_support import ROOT, make_manifest, TEXT, AuthoredReading, digest, read
from speech_xray.reference.manifest import load_manifest
from speech_xray.reference.profile_builder import build_reference_profile
from speech_xray.reference.models import ArtifactReference
from speech_xray.japanese.alignment_input import load_alignment
from speech_xray.deviation.inputs import verified_reference
from speech_xray.stress.artifacts import ROOT as PRIVATE_ROOT, load, save
from speech_xray.stress.pipeline import analyse
from speech_xray.stress.runner import run
from speech_xray.corpus.batch_plan import pipeline_configuration


class PipelineContractTests(unittest.TestCase):
    def setUp(self):
        PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=PRIVATE_ROOT, prefix='authored-unit-')
        self.directory = Path(self.temp.name)
        path = make_manifest(self.directory)
        self.manifest = load_manifest(path)
        self.entry = self.manifest.entries[0]
        profile = build_reference_profile(self.manifest)
        profile_path = self.directory/'authored-profile.json';profile_path.write_text(profile.to_json(), encoding='utf-8')
        self.reference = verified_reference(path, ArtifactReference(str(profile_path), digest(profile_path)), 'authored-fixture-v1')
        self.refs = self.entry.to_dict()['sources']
        self.base = {'base_id': 'authored-base', 'speaker_id': self.entry.speaker_id, 'prompt_id': self.entry.prompt_id,
            'surface': TEXT, 'reading': TEXT, 'target': self.manifest.target.to_dict(),
            'sources': self.refs, 'reference_profile': {'path': str(profile_path), 'sha256': digest(profile_path)},
            'reference_manifest': {'path': str(path), 'sha256': digest(path)}}

    def tearDown(self): self.temp.cleanup()

    def test_analysis_signature_excludes_factor_and_ground_truth(self):
        names = set(inspect.signature(analyse).parameters)
        self.assertFalse(names & {'factor', 'ground_truth', 'start', 'end', 'target_sample_start', 'target_sample_end'})

    def test_authored_existing_mapper_acoustic_integrity_normalization_and_formulas(self):
        alignment = load_alignment(self.refs['alignment']['path'])
        with patch('speech_xray.stress.pipeline.parse_textgrid', return_value=alignment), patch(
                'speech_xray.stress.pipeline.SudachiReadingProvider', return_value=AuthoredReading()):
            answer = analyse('authored-case', self.refs['audio']['path'], self.refs['alignment']['path'],
                self.refs['transcript']['path'], self.base, self.directory/'analysis', self.reference, mfa_completed=True)
        self.assertEqual(answer['final_status'], 'EVIDENCE_AVAILABLE', answer['reason_codes'])
        self.assertTrue(answer['checks']['mora_span_preserved'])
        self.assertEqual(answer['deviation']['reference_n'], 5)  # authored math population only
        self.assertTrue(answer['deviation']['candidate_speaker_in_reference'])
        self.assertIn('NO_VOICED_FRAMES', answer['failure_categories'])
        self.assertFalse(answer['deviation']['reference_export_allowed'])
        self.assertNotIn('ground_truth', answer)

    def test_missing_textgrid_retains_failure_and_reason(self):
        answer = analyse('authored-missing', self.refs['audio']['path'], self.directory/'absent.TextGrid',
            self.refs['transcript']['path'], self.base, self.directory/'missing-analysis', self.reference)
        self.assertEqual(answer['final_status'], 'ABSTAIN')
        self.assertEqual(answer['failure_categories'], ['MFA_FAILURE'])
        self.assertFalse(answer['checks']['mfa_completed'])
        self.assertTrue((self.directory/'missing-analysis/pipeline-result.json').exists())

    def test_transcript_change_abstains_before_analysis(self):
        path = self.directory/'changed.lab';path.write_text('AUTHORED DIFFERENT TEXT')
        answer = analyse('authored-transcript', self.refs['audio']['path'], self.refs['alignment']['path'],
            path, self.base, self.directory/'transcript-analysis', self.reference)
        self.assertEqual(answer['reason_codes'], ['TRANSCRIPT_CHANGED_FROM_ACCEPTED_PROMPT'])

    def test_native_loader_rejects_perturbed_material_kind(self):
        value = read(Path(self.manifest.source));value['dataset']['material_kind'] = 'CONTROLLED_DURATION_PERTURBATION'
        path = self.directory/'never-native.json';save(path, value)
        with self.assertRaises(ValueError): load_manifest(path)

    def test_dry_plan_numeric_configuration_round_trip(self):
        plan = {'configuration': pipeline_configuration(run_label='controlled-perturbation'),
            'bases': [{'base_id': 'authored', 'target': {'target_id': 'authored-target'}}]}
        path = self.directory/'authored-plan.json';save(path, plan)
        with patch('speech_xray.stress.runner.mfa_align') as aligner:
            answer = run(path, self.directory/'dry')
        self.assertTrue(answer['dry_run']);self.assertEqual(answer['case_count'], 12)
        aligner.assert_not_called()

    def test_core_and_evaluation_have_no_stress_reverse_dependency(self):
        package = ROOT/'services/speech-api/src/speech_xray'
        for folder in ('alignment', 'japanese', 'acoustics', 'reference', 'deviation', 'evaluation'):
            for path in (package/folder).glob('*.py'):
                self.assertNotIn('speech_xray.stress', path.read_text(encoding='utf-8'))
