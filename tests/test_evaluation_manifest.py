from dataclasses import FrozenInstanceError
from pathlib import Path
from decimal import Decimal
import unittest
from evaluation_test_support import workspace,make_dataset,changed,pinned
from reference_test_support import read,write_json
from speech_xray.evaluation.learner_manifest import load_learner_manifest,validate_import
from speech_xray.evaluation.dataset import create_run,load_splits,selection_contract,require_reference_speaker
from speech_xray.evaluation.serialization import save,serialize,decode


class LearnerManifestTests(unittest.TestCase):
    def setUp(self):self.root=workspace(self);self.path,self.entry=make_dataset(self.root/'source')

    def test_valid_external_chinese_metadata_preserved(self):
        dataset=load_learner_manifest(self.path)
        self.assertEqual(dataset.data['observations'][0]['speaker_native_language'],'zh')
        self.assertEqual(validate_import(dataset)[0]['status'],'IMPORTED')
        self.assertEqual(dataset.data['dataset_role'],'LEARNER')

    def test_controlled_source_binds_original_authored_prompt(self):
        path,_=make_dataset(self.root/'controlled',source='CONTROLLED_LEARNER_RECORDING')
        self.assertEqual(validate_import(load_learner_manifest(path))[0]['status'],'IMPORTED')

    def test_native_language_unknown_stays_unknown_not_inferred(self):
        path,_=make_dataset(self.root/'unknown',language=None)
        self.assertIsNone(load_learner_manifest(path).data['observations'][0]['speaker_native_language'])

    def test_missing_provenance_rejected(self):
        with self.assertRaises(ValueError):changed(self.path,lambda d:d['observations'][0].__setitem__('source_provenance',None))

    def test_unknown_speaker_rejected(self):
        with self.assertRaises(ValueError):changed(self.path,lambda d:d['observations'][0].__setitem__('speaker_id','unknown'))

    def test_speaker_language_must_match_pinned_metadata(self):
        with self.assertRaises(ValueError):changed(self.path,lambda d:d['observations'][0].__setitem__('speaker_native_language','en'))

    def test_missing_transcript_returns_external_abstention(self):
        def mutate(d):d['observations'][0].update(transcript=None,transcript_source=None)
        dataset=changed(self.path,mutate)
        self.assertEqual(validate_import(dataset)[0]['status'],'ABSTAIN_UNSUPPORTED_EXTERNAL_SAMPLE')
        self.assertIn('TRANSCRIPT_MISSING',validate_import(dataset)[0]['reason_codes'])

    def test_missing_audio_returns_external_abstention(self):
        dataset=changed(self.path,lambda d:d['observations'][0].__setitem__('audio_identity',None))
        self.assertIn('AUDIO_MISSING',validate_import(dataset)[0]['reason_codes'])

    def test_multi_speaker_sample_abstains(self):
        dataset=changed(self.path,lambda d:d['observations'][0]['source_provenance'].__setitem__('task_structure','MULTI_SPEAKER'))
        self.assertEqual(validate_import(dataset)[0]['status'],'ABSTAIN_UNSUPPORTED_EXTERNAL_SAMPLE')

    def test_original_corpus_label_separate_and_optional(self):
        d=load_learner_manifest(self.path).data
        self.assertIn('source_label',d['observations'][0]['corpus_annotation'])
        path,_=make_dataset(self.root/'absent',corpus_label=False)
        self.assertIsNone(load_learner_manifest(path).data['observations'][0]['corpus_annotation'])

    def test_import_cannot_claim_preexisting_human_model_state(self):
        with self.assertRaises(ValueError):changed(self.path,lambda d:d['observations'][0].__setitem__('annotation_status','MODEL_EVIDENCE_ATTACHED'))

    def test_learner_role_cannot_be_reference(self):
        with self.assertRaises(ValueError):changed(self.path,lambda d:d.__setitem__('dataset_role','REFERENCE_SPEAKER'))

    def test_unverified_local_analysis_not_yes(self):
        for value in ('NO','UNKNOWN',True):
            original=read(self.path);original['rights']['permissions']['local_analysis']=value;write_json(self.path,original)
            with self.assertRaises(ValueError):load_learner_manifest(self.path)

    def test_publication_unknown_is_preserved(self):
        rights=load_learner_manifest(self.path).data['rights']['permissions']
        self.assertEqual(rights['raw_audio_redistribution'],'UNKNOWN')
        self.assertEqual(rights['aggregate_publication'],'UNKNOWN')

    def test_rights_source_classes_cannot_mix(self):
        with self.assertRaises(ValueError):changed(self.path,lambda d:d['rights'].__setitem__('source_type','CONTROLLED_LEARNER_RECORDING'))

    def test_real_material_cannot_use_authored_metadata(self):
        with self.assertRaises(ValueError):changed(self.path,lambda d:d.__setitem__('material_kind','REAL_LEARNER_AUDIO'))

    def test_active_manifest_and_sources_must_remain_private(self):
        with self.assertRaises(ValueError):load_learner_manifest(self.root.parents[2]/'public.json')
        with self.assertRaises(ValueError):changed(self.path,lambda d:d['observations'][0]['speaker_metadata_source'].__setitem__('path',str(self.root.parents[2]/'outside.json')))

    def test_duplicate_json_and_nonfinite_input_rejected(self):
        for raw in ('{"schema_version":"0.1","schema_version":"0.1"}','{"schema_version":NaN}'):
            self.path.write_text(raw)
            with self.assertRaises(ValueError):load_learner_manifest(self.path)

    def test_snapshot_data_and_role_are_immutable(self):
        dataset=load_learner_manifest(self.path);data=dataset.data;data['dataset_role']='REFERENCE'
        self.assertEqual(dataset.data['dataset_role'],'LEARNER')
        with self.assertRaises(FrozenInstanceError):dataset.sha256='0'*64

    def test_changed_manifest_invalidates_import(self):
        dataset=load_learner_manifest(self.path);self.path.write_bytes(self.path.read_bytes()+b' ')
        with self.assertRaises(ValueError):validate_import(dataset)


class SpeakerSplitTests(unittest.TestCase):
    def setUp(self):
        self.root=workspace(self);path,_=make_dataset(self.root/'source');self.dataset=load_learner_manifest(path)

    def test_one_speaker_one_split(self):
        run=create_run('authored-run',[self.dataset],[('authored-learner','calibration')])
        self.assertEqual(run.assignments,(('authored-learner','calibration'),))

    def test_same_speaker_cannot_cross_calibration_and_test(self):
        with self.assertRaisesRegex(ValueError,'SPEAKER_IN_MULTIPLE_SPLITS'):
            create_run('authored-run',[self.dataset],[('authored-learner','calibration'),('authored-learner','held_out_test')])

    def test_reference_leakage_firewall(self):
        with self.assertRaisesRegex(ValueError,'ROLE_FIREWALL'):
            create_run('authored-run',[self.dataset],[('authored-learner','calibration')],['authored-learner'])

    def test_missing_and_unknown_speaker_assignments_rejected(self):
        for assignments in ([],[('unknown','development')]):
            with self.assertRaises(ValueError):create_run('authored-run',[self.dataset],assignments)

    def test_held_out_selection_forbidden_and_current_selection_always_false(self):
        for split in ('development','calibration','held_out_test'):
            run=create_run('authored-run',[self.dataset],[('authored-learner',split)])
            contract=selection_contract(run,'authored-learner')
            self.assertFalse(contract['selection_allowed_in_task011'])
            self.assertEqual(contract['selection_allowed_in_later_task'],split=='calibration')

    def test_learner_cannot_export_as_native_reference(self):
        run=create_run('authored-run',[self.dataset],[('authored-learner','development')],['native-only'])
        with self.assertRaises(ValueError):require_reference_speaker(run,'authored-learner')
        require_reference_speaker(run,'native-only')

    def test_split_file_pins_dataset_version(self):
        path=self.root/'splits.json';value={'schema_version':'0.1','evaluation_run_id':'authored-run',
            'dataset_hashes':[self.dataset.sha256],'assignments':[{'speaker_id':'authored-learner','split':'held_out_test'}]}
        save(path,value)
        self.assertEqual(load_splits(path,[self.dataset]).assignments,(('authored-learner','held_out_test'),))
        value['dataset_hashes']=['0'*64];write_json(path,value)
        with self.assertRaises(ValueError):load_splits(path,[self.dataset])

    def test_run_identity_cannot_reassign_role_or_split(self):
        run=create_run('authored-run',[self.dataset],[('authored-learner','held_out_test')])
        with self.assertRaises(FrozenInstanceError):run.assignments=(('authored-learner','calibration'),)

    def test_deterministic_private_serialization(self):
        value=self.dataset.data
        a=save(self.root/'canonical.json',value);b=save(self.root/'canonical.json',value)
        self.assertEqual(a,b);self.assertEqual(decode(serialize(value)),value)
        with self.assertRaises(ValueError):save(self.root/'canonical.json',{'changed':True})
