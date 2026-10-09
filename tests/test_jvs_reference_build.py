"""Authored control/structured fixtures; no real corpus numbers or speech."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from reference_test_support import ROOT,make_manifest
from speech_xray.jvs_reference.build import qualify,counts,save_verified,sanity
from speech_xray.jvs_reference.cache import safe_directory,read_control,validate_artifacts
from speech_xray.jvs_reference.lineage import DEFERRED,BASELINE
from speech_xray.jvs_reference.observations import utterance,admit,map_target
from speech_xray.reference.manifest import load_manifest
from speech_xray.reference.profile_builder import build_reference_profile
from speech_xray.corpus.batch_plan import digest


class JvsReferenceBuildTests(unittest.TestCase):
    def setUp(self):
        parent=ROOT/'data/private/tests';parent.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def rows(self,n=5):
        return [{'speaker_id':f'AUTHORED-{i}','audio_sha256':str(i),'status':'VALID',
            'alignment_success':True,'mapping_success':True,'acoustic_success':True,
            'normalization_success':True} for i in range(n)]

    def test_qualification_order_determinism_and_gate(self):
        rows=self.rows()
        self.assertEqual(qualify(rows),qualify(list(reversed(rows))))
        self.assertEqual(qualify(rows),'QUALIFIED_FOR_FULL_BUILD')
        self.assertEqual(qualify(rows[:4]),'DEFERRED_INSUFFICIENT_VALID_OBSERVATIONS')

    def test_duplicate_speakers_rejected(self):
        rows=self.rows();rows[-1]['speaker_id']=rows[0]['speaker_id']
        with self.assertRaisesRegex(ValueError,'DUPLICATE_SPEAKER'):qualify(rows)

    def test_duplicate_audio_rejected(self):
        rows=self.rows();rows[-1]['audio_sha256']=rows[0]['audio_sha256']
        with self.assertRaisesRegex(ValueError,'DUPLICATE_AUDIO'):qualify(rows)

    def test_frame_fields_do_not_inflate_independence(self):
        rows=self.rows(1);rows[0]['f0_frames']=[1]*100
        self.assertEqual(counts(rows)['valid_reference_observation_speakers'],1)
        self.assertEqual(qualify(rows),'DEFERRED_INSUFFICIENT_VALID_OBSERVATIONS')
        path=make_manifest(self.root,[('AUTHORED','take','150','9700')])
        manifest=load_manifest(path)
        acoustic,_=read_control(dict(manifest.entries[0].sources)['acoustic_evidence'].path)
        self.assertEqual(acoustic['track']['frame_count'],100)
        profile=build_reference_profile(manifest)
        self.assertEqual(len(profile.speakers),1)
        self.assertEqual(dict(profile.statistics)['raw_duration_ms'].count,1)
        self.assertEqual(profile.profile_status,'INSUFFICIENT_SPEAKERS')

    def test_stage_failures_preserved(self):
        rows=self.rows();rows[0].update(status='TARGET_NOT_MAPPED',reason='DECLARED_WORD_BOUNDARY_NOT_PRESERVED',mapping_success=False,acoustic_success=False,normalization_success=False)
        result=counts(rows)
        self.assertEqual((result['attempted_speakers'],result['mapped_speakers'],result['valid_reference_observation_speakers']),(5,4,4))
        self.assertEqual(result['failure_reasons'],{'DECLARED_WORD_BOUNDARY_NOT_PRESERVED':1})

    def test_alignment_and_mapping_deferred(self):
        rows=self.rows();
        for row in rows:row.update(status='ALIGNMENT_FAILED',alignment_success=False,mapping_success=False)
        self.assertEqual(qualify(rows),'DEFERRED_ALIGNMENT_FAILURE')
        for row in rows:row['alignment_success']=True
        self.assertEqual(qualify(rows),'DEFERRED_MAPPING_FAILURE')

    def test_missing_audio_is_explicit(self):
        value=utterance({'audio_path':str(self.root/'missing.wav')},{},self.root)
        self.assertEqual(value['status'],'AUDIO_MISSING')

    def test_alignment_failure_skips_acoustics(self):
        audio=self.root/'authored.ref';audio.write_text('NOT_AUDIO')
        with patch('speech_xray.jvs_reference.observations.extract_acoustic_evidence') as extractor:
            value=utterance({'audio_path':str(audio),'audio_sha256':digest(audio)}, {'status':'ALIGNMENT_FAILED'},self.root)
        self.assertEqual(value['status'],'ALIGNMENT_FAILED');extractor.assert_not_called()

    def test_upstream_acoustic_failure_retained(self):
        job={'speaker_id':'AUTHORED','prompt_id':'P','audio_sha256':'a'}
        row,entry,_=admit({'target_id':'T'},{},job,{'status':'ACOUSTIC_EXTRACTION_FAILED','reason':'AUTHORED_FAILURE'})
        self.assertEqual(row['reason'],'AUTHORED_FAILURE');self.assertIsNone(entry)

    def test_cache_mutation_and_config_change_rejected(self):
        artifact=self.root/'authored.txt';artifact.write_text('AUTHORED')
        receipt={'signature':'version-A','artifacts':{'source':{'path':str(artifact),'sha256':digest(artifact)}}}
        validate_artifacts(receipt,'version-A')
        with self.assertRaises(ValueError):validate_artifacts(receipt,'version-B')
        artifact.write_text('MUTATED')
        with self.assertRaises(ValueError):validate_artifacts(receipt,'version-A')

    def test_complete_cache_receipt_cannot_omit_evidence(self):
        with self.assertRaisesRegex(ValueError,'COMPLETE_EVIDENCE'):
            validate_artifacts({'status':'PASS','signature':'authored','artifacts':{}},'authored')

    def test_textgrid_must_match_saved_parsed_alignment(self):
        from speech_xray.alignment.textgrid_parser import parse_textgrid
        grid=self.root/'authored.TextGrid';grid.write_bytes((ROOT/'tests/fixtures/alignment.TextGrid').read_bytes())
        alignment=self.root/'alignment.json';alignment.write_text(parse_textgrid(grid).to_json(),encoding='utf-8')
        refs={name:{'path':str(grid),'sha256':digest(grid)} for name in ('audio','transcript','textgrid','mora_analysis','acoustic_evidence')}
        refs['alignment']={'path':str(alignment),'sha256':digest(alignment)}
        value={'status':'PASS','signature':'authored','artifacts':refs}
        validate_artifacts(value,'authored')
        text=alignment.read_text(encoding='utf-8').replace('authored.TextGrid','changed.TextGrid')
        alignment.write_text(text,encoding='utf-8');refs['alignment']['sha256']=digest(alignment)
        with self.assertRaisesRegex(ValueError,'PARSED_ALIGNMENT_MISMATCH'):validate_artifacts(value,'authored')

    def test_resume_never_overwrites_changed_canonical_artifact(self):
        path=self.root/'control.json';first=save_verified(path,{'state':'AUTHORED'})
        self.assertEqual(first,save_verified(path,{'state':'AUTHORED'}))
        with self.assertRaises(ValueError):save_verified(path,{'state':'CHANGED'})

    def test_strict_controls_reject_duplicates_nonfinite(self):
        for text in ('{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}','{"x":1e999}'):
            path=self.root/'bad.json';path.write_text(text)
            with self.assertRaises(ValueError):read_control(path)

    def test_private_source_firewall(self):
        for path in (ROOT/'tests/fixtures',ROOT.parent):
            with self.assertRaises(ValueError):safe_directory(path)

    def test_existing_math_and_sanity_reused(self):
        profile=build_reference_profile(load_manifest(make_manifest(self.root)))
        sanity(profile)
        self.assertEqual(len(profile.speakers),5)
        self.assertEqual(profile.to_dict()['independence_unit'],'SPEAKER')

    def test_mapping_reuses_exact_declared_identity(self):
        from speech_xray.external_jvs.smoke import aligned_word_identity
        import speech_xray.jvs_reference.observations as adapter
        self.assertIs(adapter.aligned_word_identity,aligned_word_identity)
        target={'word_index':0,'surface_hint':'AUTHORED','expected_word_reading':'AUTHORED',
            'word_mora_indices':[0,1],'candidate_type':'KANA_SEQUENCE','vowel_class':'O'}
        analysis=SimpleNamespace(words=(SimpleNamespace(surface='AUTHORED',reading_result=SimpleNamespace(reading='AUTHORED')),),long_vowel_spans=(),morae=())
        self.assertEqual(map_target(target,{'words':[{'surface':'AUTHORED'}]},analysis),(None,'DECLARED_LEXICAL_TARGET_NOT_UNIQUELY_MAPPED'))

    def test_lineage_deferred_ids_stay_disjoint(self):
        self.assertEqual(len(DEFERRED),3)
        self.assertEqual(BASELINE,'872bcedeccc88584be66e6a0653070925a4bd4eb')

    def batch_job(self):
        audio=self.root/'authored.ref';audio.write_text('SELF_AUTHORED_NOT_AUDIO')
        return {'speaker_id':'AUTHORED','prompt_id':'AUTHORED-P','audio_path':str(audio),
            'audio_sha256':digest(audio),'text':'AUTHORED','source_type':'TEST_FIXTURE'}

    def test_primary_mfa_batch_cache_and_corrupt_resume(self):
        from speech_xray.jvs_reference.mfa_batch import align_batch
        job=self.batch_job();calls=[]
        def align(paths,recording):
            calls.append(recording['speaker_id']);grid=Path(paths['textgrid']);grid.parent.mkdir(parents=True)
            grid.write_bytes((ROOT/'tests/fixtures/alignment.TextGrid').read_bytes())
        with patch('speech_xray.jvs_reference.mfa_batch.batch_signature',return_value=('authored-version',{})),patch('speech_xray.jvs_reference.mfa_batch.worker_models',return_value=[]):
            first=align_batch([job],self.root/'batches',self.root/'models',align)
            second=align_batch([job],self.root/'batches',self.root/'models',align)
            self.assertTrue(second['execution_cache_hit']);self.assertEqual(len(calls),1)
            Path(first['results']['AUTHORED-P']['textgrid']).write_text('CORRUPT')
            third=align_batch([job],self.root/'batches',self.root/'models',align)
        self.assertFalse(third['execution_cache_hit']);self.assertEqual(len(calls),2)
        self.assertEqual(len(third['invalid_previous_receipts']),1)

    def test_primary_mfa_failure_is_structured_and_preserved(self):
        from speech_xray.jvs_reference.mfa_batch import align_batch
        job=self.batch_job()
        def fail(paths,recording):raise RuntimeError('AUTHORED_MFA_FAILURE')
        with patch('speech_xray.jvs_reference.mfa_batch.batch_signature',return_value=('authored-version',{})),patch('speech_xray.jvs_reference.mfa_batch.worker_models',return_value=[]):
            value=align_batch([job],self.root/'batches',self.root/'models',fail)
        self.assertEqual(value['results']['AUTHORED-P']['status'],'ALIGNMENT_FAILED')

    def test_incomplete_batch_is_retained_and_not_trusted(self):
        from speech_xray.jvs_reference.mfa_batch import align_batch
        job=self.batch_job();partial=self.root/'batches/authored-version/attempt-000';partial.mkdir(parents=True)
        (partial/'partial.txt').write_text('INCOMPLETE')
        def fail(paths,recording):raise ValueError('AUTHORED_INTERRUPTION')
        with patch('speech_xray.jvs_reference.mfa_batch.batch_signature',return_value=('authored-version',{})),patch('speech_xray.jvs_reference.mfa_batch.worker_models',return_value=[]):
            value=align_batch([job],self.root/'batches',self.root/'models',fail)
        self.assertTrue((partial/'partial.txt').is_file())
        self.assertIn('attempt-001',value['results']['AUTHORED-P']['transcript'])

    def test_batch_cannot_merge_independent_speakers(self):
        from speech_xray.jvs_reference.mfa_batch import align_batch
        job=self.batch_job();other={**job,'speaker_id':'OTHER','prompt_id':'OTHER-P'}
        with self.assertRaisesRegex(ValueError,'ONE_SPEAKER'):align_batch([job,other],self.root,self.root)

    def lineage_fixture(self):
        archive=self.root/'authored.zip';archive.write_bytes(b'NOT_JVS_ARCHIVE_IDENTITY_TEST')
        deferred=[{'target_id':t,'orthographic_pattern':'AUTHORED','vowel_class':'O'} for t in sorted(DEFERRED)]
        stable=[{'target_id':f'AUTHORED-{i}'} for i in range(17)]
        replacements=[{'target_id':f'REPLACEMENT-{i}','replaces_deferred_target_id':t['target_id'],
            'orthographic_pattern':'AUTHORED','vowel_class':'O'} for i,t in enumerate(deferred[:2])]
        config={k:{} for k in ('alignment','reading','environment_locks','model_resource_metadata_sha256','model_resources','analysis_code_sha256','acoustics')}
        audit={'recommendation':{'selected_targets':stable+deferred},'inventory':{'source_type':'EXTERNAL_RESEARCH_CORPUS',
            'corpus_root':str(self.root),'transcript_sources':[]},'discovery':{}}
        smoke={'source_type':'EXTERNAL_RESEARCH_CORPUS','configuration':config,
            'reviewed_recommendation':{'selected_targets':stable+replacements,'deferred_targets':deferred}}
        receipt={'archive_path':str(archive),'archive_sha256':digest(archive)}
        return audit,smoke,receipt,config

    def test_actual_lineage_validation_20_minus3_plus2(self):
        from speech_xray.jvs_reference.lineage import load_inputs
        audit,smoke,receipt,config=self.lineage_fixture()
        with patch('speech_xray.jvs_reference.lineage.read_json',side_effect=[(audit,'a'),(smoke,'b'),(receipt,'c')]),patch('speech_xray.jvs_reference.lineage.pipeline_configuration',return_value=config):
            result=load_inputs(self.root)
        self.assertEqual(len(result['targets']),19)
        self.assertEqual(result['lineage']['arithmetic'],'20 - 3 + 2 = 19')
        self.assertEqual(result['lineage']['distinct_reviewed_target_ids'],22)

    def test_lineage_duplicate_and_source_reclassification_rejected(self):
        from speech_xray.jvs_reference.lineage import load_inputs
        for mode in ('duplicate','source'):
            audit,smoke,receipt,config=self.lineage_fixture()
            if mode=='duplicate':smoke['reviewed_recommendation']['selected_targets'][-1]=smoke['reviewed_recommendation']['selected_targets'][0]
            else:audit['inventory']['source_type']='SELF_COLLECTED_REFERENCE'
            with patch('speech_xray.jvs_reference.lineage.read_json',side_effect=[(audit,'a'),(smoke,'b'),(receipt,'c')]),patch('speech_xray.jvs_reference.lineage.pipeline_configuration',return_value=config):
                with self.assertRaises(ValueError):load_inputs(self.root)

    def test_lineage_primary_configuration_change_rejected(self):
        from speech_xray.jvs_reference.lineage import load_inputs
        audit,smoke,receipt,config=self.lineage_fixture();changed={**config,'alignment':{'changed':True}}
        with patch('speech_xray.jvs_reference.lineage.read_json',side_effect=[(audit,'a'),(smoke,'b'),(receipt,'c')]),patch('speech_xray.jvs_reference.lineage.pipeline_configuration',return_value=changed):
            with self.assertRaisesRegex(ValueError,'CONFIGURATION_CHANGED'):load_inputs(self.root)

    def test_acoustic_stage_independent_of_reference_admission(self):
        from reference_test_support import bundle,TEXT
        from speech_xray.jvs_reference.stage_evidence import observed_stages
        entry=bundle(self.root,'AUTHORED','take')
        target={'word_index':0,'surface_hint':TEXT,'expected_word_reading':TEXT,'word_mora_indices':[0,1],
            'candidate_type':'PROLONGED_MARK','vowel_class':'O'}
        result=observed_stages(target,{'words':[{'surface':TEXT}]},{'status':'PASS','artifacts':entry['sources']})
        self.assertTrue(result['mapping_success']);self.assertTrue(result['acoustic_success'])
        self.assertEqual(result['acoustic_span_status'],'OK')

    def test_bundle_input_cannot_be_swapped_between_speakers(self):
        from reference_test_support import bundle,TEXT
        from speech_xray.jvs_reference.stage_evidence import verify_job_sources
        entry=bundle(self.root,'AUTHORED','take');refs=entry['sources']
        lab=Path(refs['transcript']['path']);lab.write_text(TEXT+'\n',encoding='utf-8');refs['transcript']['sha256']=digest(lab)
        job={'audio_path':refs['audio']['path'],'audio_sha256':refs['audio']['sha256'],'text':TEXT}
        verify_job_sources(job,{'status':'PASS','artifacts':refs})
        with self.assertRaisesRegex(ValueError,'AUDIO_IDENTITY_MISMATCH'):
            verify_job_sources({**job,'audio_sha256':'0'*64},{'status':'PASS','artifacts':refs})
        with self.assertRaisesRegex(ValueError,'TRANSCRIPT_IDENTITY_MISMATCH'):
            verify_job_sources({**job,'text':'CHANGED_AUTHORED_TEXT'},{'status':'PASS','artifacts':refs})


if __name__=='__main__':unittest.main()
