"""Local contracts only: no acquisition, login, scraping or native-reference export."""
from pathlib import Path
import re
from speech_xray.reference.manifest import keys,text,sha256
from speech_xray.reference.json_input import read_json
from speech_xray.corpus.batch_plan import digest
from .models import LearnerDataset, SourceType, WorkflowState
from .serialization import serialize,private_path
from .validation import identifier,artifact,target
from .rights import validate_rights

MANIFEST_FIELDS = ('schema_version','dataset_id','dataset_version','evaluation_run_id','source_type',
                   'dataset_role','material_kind','rights','observations')
OBSERVATION_FIELDS = ('observation_id','speaker_id','speaker_native_language','speaker_metadata_source',
    'utterance_id','audio_identity','transcript','transcript_source','target','source_provenance',
    'corpus_annotation','annotation_status','analysis_status','project_prompt')


def load_learner_manifest(path):
    source=private_path(path);value,sha=read_json(source)
    keys(value,MANIFEST_FIELDS)
    if value['schema_version']!='0.1' or value['dataset_role']!='LEARNER':raise ValueError('LEARNER_ROLE_REQUIRED')
    for key in ('dataset_id','dataset_version','evaluation_run_id'):identifier(value[key])
    SourceType(value['source_type'])
    if value['material_kind'] not in {'REAL_LEARNER_AUDIO','AUTHORED_STRUCTURAL_FIXTURE'}:
        raise ValueError('INVALID_LEARNER_MATERIAL_KIND')
    if not isinstance(value['observations'],list):raise ValueError('EXPECTED_OBSERVATIONS_ARRAY')
    validate_rights(value['rights'],value,source.parent)
    ids=set();audio_ids=set();utterances={};speakers={}
    for row in value['observations']:
        keys(row,OBSERVATION_FIELDS)
        for key in ('observation_id','speaker_id','utterance_id'):identifier(row[key])
        if row['observation_id'] in ids:raise ValueError('DUPLICATE_OBSERVATION_ID')
        ids.add(row['observation_id'])
        language=row['speaker_native_language']
        if language is not None and (not isinstance(language,str) or not re.fullmatch('[a-z]{2,3}(?:-[A-Za-z0-9]+)*',language)):
            raise ValueError('INVALID_DECLARED_NATIVE_LANGUAGE')
        meta=artifact(row['speaker_metadata_source'],source.parent)
        metadata,metadata_sha=read_json(Path(meta['path']))
        keys(metadata,('speaker_id','native_language','metadata_basis'))
        if (metadata['speaker_id']!=row['speaker_id'] or metadata['native_language']!=language
                or metadata['metadata_basis'] not in {'PARTICIPANT_SELF_REPORT','CORPUS_METADATA','AUTHORED_FIXTURE'}
                or (value['material_kind']=='REAL_LEARNER_AUDIO' and metadata['metadata_basis']=='AUTHORED_FIXTURE')):
            raise ValueError('SPEAKER_METADATA_BINDING_INVALID')
        if value['material_kind']=='REAL_LEARNER_AUDIO':
            expected='PARTICIPANT_SELF_REPORT' if value['source_type']=='CONTROLLED_LEARNER_RECORDING' else 'CORPUS_METADATA'
            if metadata['metadata_basis']!=expected:raise ValueError('SPEAKER_METADATA_SOURCE_CLASS_CONFLICT')
        signature=(language,meta['sha256'])
        if row['speaker_id'] in speakers and speakers[row['speaker_id']]!=signature:
            raise ValueError('SPEAKER_METADATA_CONFLICT')
        speakers[row['speaker_id']]=signature
        artifact(row['audio_identity'],source.parent,required=False)
        artifact(row['transcript_source'],source.parent,required=False)
        if row['transcript'] is not None:
            text(row['transcript'],'transcript')
            ref=row['transcript_source']
            if ref is None or Path(artifact(ref,source.parent)['path']).read_text(encoding='utf-8')!=row['transcript']:
                raise ValueError('TRANSCRIPT_SOURCE_CONTENT_MISMATCH')
        elif row['transcript_source'] is not None:raise ValueError('TRANSCRIPT_CONTENT_MISSING')
        if row['target'] is not None:target(row['target'])
        p=row['source_provenance']
        keys(p,('provider','record_id','task_structure','source_record'))
        text(p['provider'],'provider');identifier(p['record_id']);artifact(p['source_record'],source.parent)
        if p['task_structure'] not in {'SINGLE_SPEAKER_READING','SINGLE_SPEAKER_TRANSCRIBED','MULTI_SPEAKER','UNKNOWN'}:
            raise ValueError('INVALID_TASK_STRUCTURE')
        corpus=row['corpus_annotation']
        if corpus is not None:
            keys(corpus,('source_label','source_label_provenance','source_record'))
            text(corpus['source_label'],'corpus label');text(corpus['source_label_provenance'],'label provenance')
            artifact(corpus['source_record'],source.parent)
            if value['source_type']!='EXTERNAL_LEARNER_CORPUS':raise ValueError('CORPUS_LABEL_SOURCE_CLASS_CONFLICT')
        if row['annotation_status']!=WorkflowState.UNANNOTATED or row['analysis_status']!='NOT_ANALYSED':
            raise ValueError('IMPORT_CANNOT_ASSERT_DERIVED_WORKFLOW_STATE')
        prompt=row['project_prompt']
        if value['source_type']=='CONTROLLED_LEARNER_RECORDING':
            keys(prompt,('pack_path','pack_sha256','prompt_id'))
            from speech_xray.corpus.prompt_manifest import load_prompt_pack
            pack=load_prompt_pack(prompt['pack_path']);sha256(prompt['pack_sha256'])
            matches=[p for p in pack.prompts if p.prompt_id==prompt['prompt_id']]
            if pack.sha256!=prompt['pack_sha256'] or len(matches)!=1 or row['transcript']!=matches[0].text:
                raise ValueError('CONTROLLED_AUTHORED_PROMPT_BINDING_INVALID')
        elif prompt is not None:raise ValueError('EXTERNAL_SAMPLE_CANNOT_CLAIM_CONTROLLED_PROMPT')
        audio=row['audio_identity']
        binding=(row['speaker_id'],row['utterance_id'])
        content=(audio['sha256'] if audio else None,row['transcript'])
        if binding in utterances and utterances[binding]!=content:raise ValueError('UTTERANCE_SOURCE_CONFLICT')
        utterances[binding]=content
        if audio:
            owners={(s,u) for s,u,h in audio_ids if h==audio['sha256']}
            if owners and binding not in owners:raise ValueError('DUPLICATE_AUDIO_ACROSS_UTTERANCES')
            audio_ids.add((*binding,audio['sha256']))
    return LearnerDataset(str(source),sha,serialize(value))


def validate_import(dataset):
    if digest(dataset.source)!=dataset.sha256:raise ValueError('LEARNER_MANIFEST_CHANGED')
    fresh=load_learner_manifest(dataset.source)
    if fresh!=dataset:raise ValueError('LEARNER_MANIFEST_OBJECT_MISMATCH')
    outcomes=[]
    for row in dataset.data['observations']:
        reasons=[]
        if row['audio_identity'] is None:reasons.append('AUDIO_MISSING')
        if row['transcript'] is None:reasons.append('TRANSCRIPT_MISSING')
        if row['source_provenance']['task_structure'] not in {'SINGLE_SPEAKER_READING','SINGLE_SPEAKER_TRANSCRIBED'}:
            reasons.append('UNSUPPORTED_TRANSCRIPT_AUDIO_STRUCTURE')
        outcomes.append({'observation_id':row['observation_id'],'speaker_id':row['speaker_id'],
            'status':('ABSTAIN_UNSUPPORTED_EXTERNAL_SAMPLE' if dataset.data['source_type']=='EXTERNAL_LEARNER_CORPUS'
                      else 'ABSTAIN_INVALID_CONTROLLED_SAMPLE') if reasons else 'IMPORTED', 'reason_codes':reasons})
    return tuple(outcomes)
