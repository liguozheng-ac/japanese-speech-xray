"""Authored silent mathematical data and metadata; never learner speech."""
from pathlib import Path
from decimal import Decimal
from dataclasses import replace
import tempfile
import json

from reference_test_support import ROOT,TEXT,bundle,read,write_json,AuthoredReading
from speech_xray.corpus.batch_plan import digest
from speech_xray.evaluation.serialization import ROOT as PRIVATE,save,identity
from speech_xray.evaluation.learner_manifest import load_learner_manifest
from speech_xray.evaluation.annotation import blind_package,begin_annotation
from speech_xray.evaluation.pipeline import load_analysis


def workspace(test):
    PRIVATE.mkdir(parents=True,exist_ok=True)
    temporary=tempfile.TemporaryDirectory(dir=PRIVATE);test.addCleanup(temporary.cleanup)
    return Path(temporary.name)


def pinned(path):return {'path':str(path),'sha256':digest(path)}


def make_dataset(directory,source='EXTERNAL_LEARNER_CORPUS',language='zh',corpus_label=True):
    directory.mkdir(parents=True,exist_ok=True)
    entry=bundle(directory,'authored-learner','take','140','2000')
    target={'target_id':'authored-eval-target','target_surface':TEXT,'target_reading':TEXT,
        'target_mora_span':2,'target_vowel_class':'O','word_mora_indices':[0,1],
        'mapping_basis':'PROLONGED_MARK','lexical_identity':TEXT}
    metadata=directory/'speaker.json'
    write_json(metadata,{'speaker_id':'authored-learner','native_language':language,'metadata_basis':'AUTHORED_FIXTURE'})
    access=directory/'authored-access.json';write_json(access,{'basis':'AUTHORED_METADATA_FIXTURE_NOT_CORPUS_ACCESS'})
    pack={'schema_version':'0.1','prompt_pack_id':'authored-fixture','prompt_pack_version':1,
        'authorship':'SELF_AUTHORED_FOR_THIS_PROJECT','reading_policy':'SUDACHI_CORE_SPLIT_B_WORD_LOCAL_EXCLUDING_SENTENCE_PUNCTUATION',
        'prompts':[{'prompt_id':'authored-fixture-001','text':TEXT,'expected_reading':TEXT,'expected_mora_count':20,
            'targets':[{'target_id':'authored-fixture-001-target-01','surface_hint':TEXT,'expected_word_reading':TEXT,
                'word_mora_indices':[0,1],'expected_reading_region':'コー','expected_candidate_type':'PROLONGED_MARK',
                'orthographic_pattern':'PROLONGED_MARK','expected_vowel_class':'O','expected_mora_span':2}]}]}
    pack_path=directory/'pack.json';write_json(pack_path,pack)
    row={'observation_id':'authored-obs','speaker_id':'authored-learner','speaker_native_language':language,
        'speaker_metadata_source':pinned(metadata),'utterance_id':'authored-utterance',
        'audio_identity':entry['sources']['audio'],'transcript':TEXT,'transcript_source':entry['sources']['transcript'],
        'target':target,'source_provenance':{'provider':'I-JAS-SHAPE-AUTHORED-ONLY' if source=='EXTERNAL_LEARNER_CORPUS'
            else 'PROJECT_AUTHORED_RECORDING_FIXTURE','record_id':'authored-export',
            'task_structure':'SINGLE_SPEAKER_TRANSCRIBED' if source=='EXTERNAL_LEARNER_CORPUS' else 'SINGLE_SPEAKER_READING',
            'source_record':pinned(access)},
        'corpus_annotation':{'source_label':'SELF_AUTHORED_CORPUS_TAG','source_label_provenance':'AUTHORED_I_JAS_SHAPE',
            'source_record':pinned(access)} if corpus_label and source=='EXTERNAL_LEARNER_CORPUS' else None,
        'annotation_status':'UNANNOTATED','analysis_status':'NOT_ANALYSED',
        'project_prompt':None if source=='EXTERNAL_LEARNER_CORPUS' else {
            'pack_path':str(pack_path),'pack_sha256':digest(pack_path),'prompt_id':'authored-fixture-001'}}
    document={'schema_version':'0.1','dataset_id':'authored-eval-dataset','dataset_version':'v1',
        'evaluation_run_id':'authored-run','source_type':source,'dataset_role':'LEARNER',
        'material_kind':'AUTHORED_STRUCTURAL_FIXTURE',
        'rights':{'record_id':'authored-rights','dataset_id':'authored-eval-dataset','dataset_version':'v1',
            'source_type':source,'access_basis':'SELF_AUTHORED_TEST_ONLY','access_record':pinned(access),
            'permissions':{'local_analysis':'YES','derived_feature_publication':'UNKNOWN','aggregate_publication':'UNKNOWN',
                'raw_audio_redistribution':'UNKNOWN','transcript_redistribution':'UNKNOWN'},'review_notes':'Not real permissions'},
        'observations':[row]}
    path=directory/'learner-manifest.json';write_json(path,document)
    return path,entry


def changed(path,mutate):
    value=read(path);mutate(value);write_json(path,value)
    return load_learner_manifest(path)


def annotation(session,who='author-A',category='LONG_VOWEL_REALIZED',obs=None):
    return {'schema_version':'0.1','annotation_id':'authored-label-'+who,
        'evaluation_run_id':session.evaluation_run_id,'observation_id':obs or session.observation_id,
        'blind_package_sha256':session.blind_package_sha256,'annotator_id':who,'category':category,
        'blind_attestation':True,'target_start_ms':None,'target_end_ms':None,
        'boundary_method':'NOT_MEASURED','annotation_tool':'AUTHORED_TEST_RECORD','notes':''}


def evidence(dataset,status='OK'):
    return {'schema_version':'0.1','representation':'LEARNER_TARGET_DURATION_EVIDENCE',
        'evaluation_run_id':dataset.data['evaluation_run_id'],'observation_id':'authored-obs',
        'dataset_identity':dataset.identity,'status':status,'model_evidence':{'fixture':'AUTHORED_NOT_PERFORMANCE'}}
