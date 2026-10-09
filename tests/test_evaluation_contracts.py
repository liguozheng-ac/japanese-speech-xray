from pathlib import Path
import importlib.util
import io
import json
from contextlib import redirect_stdout
import unittest
from evaluation_test_support import workspace,make_dataset
from reference_test_support import ROOT
from speech_xray.evaluation.learner_manifest import load_learner_manifest,MANIFEST_FIELDS,OBSERVATION_FIELDS
from speech_xray.evaluation.annotation import ANNOTATION_FIELDS
from speech_xray.evaluation.rights import RIGHTS_FIELDS


class PublicContractsTests(unittest.TestCase):
    def setUp(self):self.root=workspace(self)

    def test_schema_required_fields_match_complete_runtime_contract(self):
        for name,fields in (('learner-manifest',MANIFEST_FIELDS),('human-annotation',ANNOTATION_FIELDS),('dataset-rights',RIGHTS_FIELDS)):
            schema=json.loads((ROOT/'data/evaluation'/(name+'.schema.json')).read_text())
            self.assertEqual(set(schema['required']),set(fields));self.assertFalse(schema['additionalProperties'])
        schema=json.loads((ROOT/'data/evaluation/learner-manifest.schema.json').read_text())
        self.assertEqual(set(schema['properties']['observations']['items']['required']),set(OBSERVATION_FIELDS))
        self.assertEqual(schema['properties']['dataset_role']['const'],'LEARNER')

    def test_candidate_rights_ledger_does_not_claim_acquisition_or_permissions(self):
        ledger=json.loads((ROOT/'data/evaluation/external-dataset-rights-ledger.json').read_text())
        self.assertIsNone(ledger['access_record'])
        self.assertEqual(set(ledger['permissions'].values()),{'UNKNOWN'})

    def test_external_public_fixture_has_no_real_audio_or_transcript(self):
        fixture=json.loads((ROOT/'data/evaluation/external-import-authored-fixture.json').read_text())
        self.assertEqual(fixture['speaker_native_language'],'zh')
        self.assertIsNone(fixture['real_audio']);self.assertIsNone(fixture['real_transcript'])
        self.assertIn('AUTHORED',fixture['fixture_role'])

    def cli(self):
        spec=importlib.util.spec_from_file_location('task011_cli',ROOT/'scripts/learner_evaluation.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

    def test_local_import_cli_has_separate_source_and_private_output(self):
        path,_=make_dataset(self.root/'source');out=self.root/'import.json'
        with redirect_stdout(io.StringIO()):code=self.cli().main(['import','--manifest',str(path),'--output',str(out)])
        result=json.loads(out.read_text());self.assertEqual(code,0)
        self.assertEqual(result['source_type'],'EXTERNAL_LEARNER_CORPUS')
        self.assertEqual(result['import_outcomes'][0]['status'],'IMPORTED')

    def test_cli_refuses_public_output(self):
        path,_=make_dataset(self.root/'source')
        with redirect_stdout(io.StringIO()):code=self.cli().main(['import','--manifest',str(path),'--output',str(ROOT/'public-learner-data.json')])
        self.assertEqual(code,1);self.assertFalse((ROOT/'public-learner-data.json').exists())

    def test_cli_blind_package_omits_model_and_source_label(self):
        path,_=make_dataset(self.root/'source');out=self.root/'blind.json'
        with redirect_stdout(io.StringIO()):code=self.cli().main(['blind','--manifest',str(path),'--observation-id','authored-obs','--output',str(out)])
        self.assertEqual(code,0)
        self.assertNotIn('SELF_AUTHORED_CORPUS_TAG',out.read_text())
        self.assertNotIn('model_evidence',out.read_text())
