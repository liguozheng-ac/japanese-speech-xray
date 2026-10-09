from pathlib import Path
from dataclasses import replace,asdict
from decimal import Decimal
import unittest

from evaluation_test_support import workspace,make_dataset,changed,pinned,annotation
from deviation_test_support import reference
from reference_test_support import read,write_json,AuthoredReading,TEXT
from speech_xray.evaluation.discovery import discover_candidates
from speech_xray.evaluation.matching import reference_descriptor,match_target
from speech_xray.evaluation.learner_manifest import load_learner_manifest
from speech_xray.evaluation.dataset import create_run
from speech_xray.evaluation.pipeline import load_analysis,plan_analysis,analyse_learner
from speech_xray.evaluation.evidence import compare_learner
from speech_xray.evaluation.annotation import blind_package,begin_annotation,submit_annotation,attach_model_evidence
from speech_xray.evaluation.readiness import dataset_readiness
from speech_xray.evaluation.serialization import save,serialize,decode
from speech_xray.corpus.prompt_manifest import load_prompt_pack,validate_prompt_pack
from speech_xray.corpus.batch_plan import digest


class DiscoveryAndMatchingTests(unittest.TestCase):
    def setUp(self):
        self.root=workspace(self);path,self.entry=make_dataset(self.root/'data')
        self.dataset=load_learner_manifest(path)
        self.ref=reference(self.root/'reference');self.descriptor=reference_descriptor(self.ref)
        self.target=self.dataset.data['observations'][0]['target']

    def test_candidate_discovery_reuses_real_reading_mora_logic(self):
        result=discover_candidates('コーヒーを飲みます。')
        self.assertEqual(result['status'],'CANDIDATES_DISCOVERED')
        self.assertTrue(all(c['status']=='POSSIBLE_LONG_VOWEL_TARGET' for c in result['candidates']))
        self.assertEqual(result['candidates'][0]['target_mora_span'],2)

    def test_missing_transcript_discovery_abstains(self):
        self.assertEqual(discover_candidates(None)['status'],'ABSTAIN_UNSUPPORTED_EXTERNAL_SAMPLE')

    def test_no_candidate_is_not_annotation(self):
        result=discover_candidates('猫を見ます。')
        self.assertEqual(result['status'],'NO_LONG_VOWEL_CANDIDATE')
        self.assertNotIn('category',result)

    def test_match_does_not_require_sentence_or_target_id_identity(self):
        result=match_target(self.target,[self.descriptor])
        self.assertEqual(result['status'],'COMPATIBLE_LINGUISTIC_TARGET')
        self.assertNotEqual(self.target['target_id'],self.descriptor['reference_target']['target_id'])
        self.assertFalse(result['sentence_identity_required'])

    def test_orthography_only_cannot_match_other_position(self):
        target={**self.target,'word_mora_indices':[2,3]}
        self.assertEqual(match_target(target,[self.descriptor])['status'],'NO_COMPATIBLE_REFERENCE')

    def test_other_lexical_identity_cannot_match(self):
        target={**self.target,'lexical_identity':'authored-other-lexeme'}
        self.assertEqual(match_target(target,[self.descriptor])['status'],'NO_COMPATIBLE_REFERENCE')

    def test_reference_feature_contract_must_match(self):
        ref={**self.descriptor,'feature_contract':{**self.descriptor['feature_contract'],'normalization_version':'unsupported'}}
        self.assertEqual(match_target(self.target,[ref])['status'],'NO_COMPATIBLE_REFERENCE')

    def test_ambiguous_references_not_selected_using_duration(self):
        result=match_target(self.target,[self.descriptor,self.descriptor])
        self.assertEqual(result['reason_codes'],['AMBIGUOUS_REFERENCE'])

    def test_learner_role_cannot_be_matching_reference(self):
        ref={**self.descriptor,'dataset_role':'LEARNER'}
        self.assertEqual(match_target(self.target,[ref])['status'],'NO_COMPATIBLE_REFERENCE')

    def test_pilot_pack_authoring_qa_and_participant_blindness(self):
        from reference_test_support import ROOT
        pack=load_prompt_pack(ROOT/'data/prompts/learner-pilot-v1.json')
        self.assertEqual(validate_prompt_pack(pack)['status'],'PASS')
        self.assertEqual(len(pack.prompts),3)
        text=(ROOT/'docs/generated/learner-pilot-v1-participant-sheet.md').read_text(encoding='utf-8')
        for word in ('median','MAD','target_start_ms','expected_word_reading','desired duration'):
            self.assertNotIn(word,text)

    def test_frozen_core_has_no_evaluation_dependency(self):
        from reference_test_support import ROOT
        for module in ('alignment','japanese','acoustics','reference','deviation'):
            for path in (ROOT/'services/speech-api/src/speech_xray'/module).glob('*.py'):
                self.assertNotIn('speech_xray.evaluation',path.read_text(encoding='utf-8'))


class LearnerPipelineTests(unittest.TestCase):
    def setUp(self):
        self.root=workspace(self);self.path,self.entry=make_dataset(self.root/'data')
        self.dataset=load_learner_manifest(self.path);self.ref=reference(self.root/'reference')
        self.run=create_run('authored-run',[self.dataset],[('authored-learner','development')],
                            [s.speaker_id for s in self.ref.profile.speakers])

    def analysis(self):return load_analysis(self.dataset,'authored-obs',self.entry['sources'],self.entry['span_id'])

    def test_existing_integrity_normalization_and_task010_formulas_consumed(self):
        analysis=self.analysis();value=compare_learner(analysis,self.ref,self.run)
        self.assertEqual(value['status'],'OK',value)
        self.assertEqual(value['model_evidence']['features']['rate_normalized_duration']['ratio_to_median'],1)
        self.assertEqual(value['reference']['version'],'AUTHORED_REFERENCE_V1')
        self.assertEqual(value['candidate']['speaker_id'],'authored-learner')

    def test_invalid_analysis_object_not_compared(self):
        analysis=self.analysis()
        bad=replace(analysis,duration=replace(analysis.duration,rate_normalized_duration=Decimal(9)))
        self.assertEqual(compare_learner(bad,self.ref,self.run)['status'],'ABSTAIN_INVALID_LEARNER_EVIDENCE')

    def test_real_role_leakage_in_reference_abstains(self):
        analysis=self.analysis()
        bad=replace(self.run,learner_speakers=self.run.learner_speakers+(self.ref.profile.speakers[0].speaker_id,))
        self.assertEqual(compare_learner(analysis,self.ref,bad)['status'],'ABSTAIN_INVALID_LEARNER_EVIDENCE')

    def test_no_diagnostic_or_threshold_model_fields(self):
        value=serialize(compare_learner(self.analysis(),self.ref,self.run))
        for word in ('CORRECT','INCORRECT','TOO_SHORT','TOO_LONG','threshold','confidence','severity','score','LONG_VOWEL_REALIZED'):
            self.assertNotIn(word,value)

    def test_comparison_deterministic(self):
        a=self.analysis()
        self.assertEqual(serialize(compare_learner(a,self.ref,self.run)),serialize(compare_learner(a,self.ref,self.run)))

    def test_blind_then_attach_separated_evidence(self):
        package=blind_package(self.dataset,'authored-obs');session=begin_annotation(package)
        session=submit_annotation(session,annotation(session))
        ref=save(self.root/'model.json',compare_learner(self.analysis(),self.ref,self.run))
        session=attach_model_evidence(session,asdict(ref))
        self.assertEqual(session.state,'MODEL_EVIDENCE_ATTACHED')
        self.assertEqual(len(session.to_dict()['human_annotation']),1)

    def test_authored_fixtures_never_establish_real_data_readiness(self):
        package=blind_package(self.dataset,'authored-obs');session=submit_annotation(begin_annotation(package),annotation(begin_annotation(package)))
        ref=save(self.root/'model.json',compare_learner(self.analysis(),self.ref,self.run));session=attach_model_evidence(session,asdict(ref))
        result=dataset_readiness([self.dataset],self.run,[session])
        self.assertEqual(result['status'],'TOOLING_READY_NO_LEARNER_DATA')
        self.assertEqual(result['real_learner_speakers'],0)
        self.assertFalse(result['REAL_LABELLED_LEARNER_DATA_READY'])

    def test_dry_run_creates_no_alignment_or_analysis(self):
        result=plan_analysis(self.dataset,'authored-obs',self.root/'runs')
        self.assertEqual(result['status'],'PLANNED')
        self.assertFalse(Path(result['run_directory']).exists())
        self.assertFalse(result['native_reference_export_allowed'])

    def test_external_unsupported_sample_never_calls_aligner(self):
        dataset=changed(self.path,lambda d:d['observations'][0]['source_provenance'].__setitem__('task_structure','MULTI_SPEAKER'))
        calls=[]
        result=analyse_learner(dataset,'authored-obs',self.root/'runs',True,aligner=lambda *a:calls.append(a))
        self.assertEqual(result['status'],'ABSTAIN_UNSUPPORTED_EXTERNAL_SAMPLE');self.assertEqual(calls,[])

    def test_cross_sentence_comparison_preserves_both_transcripts(self):
        from speech_xray.japanese.alignment_input import load_alignment
        from speech_xray.alignment.models import WordInterval,PhoneInterval
        from speech_xray.japanese.long_vowel_mapper import analyze_mora
        from speech_xray.acoustics.pipeline import extract_acoustic_evidence
        from speech_xray.acoustics.mora_input import load_mora_analysis
        from speech_xray.acoustics.config import AcousticConfig
        sources=self.entry['sources'];alignment=load_alignment(sources['alignment']['path'])
        words=alignment.words[:-1]+(WordInterval('ア',Decimal(2100),Decimal(2200)),WordInterval('',Decimal(2200),Decimal(2201)))
        phones=alignment.phones[:-1]+(PhoneInterval('a',Decimal(2100),Decimal(2200)),PhoneInterval('',Decimal(2200),Decimal(2201)))
        alignment=replace(alignment,words=words,phones=phones)
        Path(sources['alignment']['path']).write_text(alignment.to_json(),encoding='utf-8')
        mora=analyze_mora(alignment,AuthoredReading());Path(sources['mora_analysis']['path']).write_text(mora.to_json(),encoding='utf-8')
        acoustic=extract_acoustic_evidence(sources['audio']['path'],load_mora_analysis(sources['mora_analysis']['path']),
            AcousticConfig(frame_length=200,hop_length=100,fmax_hz=400))
        Path(sources['acoustic_evidence']['path']).write_text(acoustic.to_json(),encoding='utf-8')
        Path(sources['transcript']['path']).write_text(TEXT+'ア',encoding='utf-8')
        for name,ref in sources.items():ref['sha256']=digest(ref['path'])
        def mutate(d):d['observations'][0].update(transcript=TEXT+'ア',transcript_source=sources['transcript'])
        dataset=changed(self.path,mutate)
        run=create_run('authored-run',[dataset],[('authored-learner','development')],[s.speaker_id for s in self.ref.profile.speakers])
        result=compare_learner(load_analysis(dataset,'authored-obs',sources,self.entry['span_id']),self.ref,run)
        self.assertEqual(result['status'],'OK',result)
        self.assertNotEqual(result['candidate']['sources']['transcript']['sha256'],self.ref.profile.manifest.transcript_sha256)
        self.assertEqual(result['candidate']['rate_context']['mora_count'],21)

    def test_pipeline_executes_unchanged_parser_mapper_extractor_with_authored_alignment(self):
        from speech_xray.acoustics.pipeline import extract_acoustic_evidence
        from speech_xray.acoustics.config import AcousticConfig
        path,entry=make_dataset(self.root/'controlled',source='CONTROLLED_LEARNER_RECORDING')
        dataset=load_learner_manifest(path);authored=read(Path(entry['sources']['alignment']['path']))
        calls=[]
        def aligner(paths,recording):
            calls.append('AUTHORED_ALIGNMENT_STUB_NOT_MFA')
            grid=Path(paths['textgrid']);grid.parent.mkdir()
            lines=['File type = "ooTextFile"','Object class = "TextGrid"','xmin = 0',
                'xmax = 2.201','tiers? <exists>','size = 2','item []:']
            for n,(name,rows) in enumerate((('words',authored['words']),('phones',authored['phones'])),1):
                lines += [f'item [{n}]:','class = "IntervalTier"',f'name = "{name}"','xmin = 0','xmax = 2.201',f'intervals: size = {len(rows)}']
                for j,row in enumerate(rows,1):
                    lines += [f'intervals [{j}]:',f'xmin = {row["start_ms"]/1000}',f'xmax = {row["end_ms"]/1000}',f'text = "{row["label"]}"']
            grid.write_text('\n'.join(lines),encoding='utf-8')
        config=AcousticConfig(frame_length=200,hop_length=100,fmax_hz=400)
        extractor=lambda audio,mora,settings:extract_acoustic_evidence(audio,mora,settings)
        result=analyse_learner(dataset,'authored-obs',self.root/'runs',True,aligner,AuthoredReading(),extractor,config)
        self.assertEqual(result['status'],'ANALYSED',result)
        self.assertEqual(len(result['analyses']),1)
        repeated=analyse_learner(dataset,'authored-obs',self.root/'runs',True,aligner,AuthoredReading(),extractor,config)
        self.assertEqual(serialize(result),serialize(repeated));self.assertEqual(len(calls),1)
        bad=lambda audio,mora,settings:extract_acoustic_evidence(audio,mora,AcousticConfig(frame_length=300,hop_length=100,fmax_hz=400))
        result=analyse_learner(dataset,'authored-obs',self.root/'bad-runs',True,aligner,AuthoredReading(),bad,config)
        self.assertEqual(result['status'],'ACOUSTIC_EXTRACTION_FAILED')
        self.assertEqual(result['reason_codes'],['EXTRACTION_CONFIG_DIFFERS_FROM_LEARNER_PLAN'])
