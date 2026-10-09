"""Learner-only orchestration of unchanged aligner/mora/acoustic/normalization code."""
from dataclasses import dataclass,asdict
from pathlib import Path
import shutil

from speech_xray.reference.models import ReferenceManifest,ReferenceEntry,TargetIdentity,ArtifactReference
from speech_xray.reference.integrity import validate_entry
from speech_xray.reference.speech_rate import measure_utterance_rate
from speech_xray.reference.normalization import normalize_duration
from speech_xray.reference.json_input import read_json
from speech_xray.corpus.batch_plan import pipeline_configuration,digest
from speech_xray.corpus.pipeline import mfa_align
from speech_xray.acoustics.audio import load_audio
from speech_xray.acoustics.config import AcousticConfig
from .learner_manifest import validate_import
from .serialization import private_path,save,serialize,identity,decode
from .validation import artifact,identifier
from .matching import signature


@dataclass(frozen=True)
class LearnerAnalysis:
    dataset: object
    observation_id: str
    sources_json: str
    span_id: str
    target_json: str
    original_span: object
    rate: object
    duration: object


def observation(dataset, observation_id):
    rows=[r for r in dataset.data['observations'] if r['observation_id']==observation_id]
    if len(rows)!=1:raise ValueError('OBSERVATION_ID_UNKNOWN')
    return rows[0]


def load_analysis(dataset, observation_id, sources, span_id):
    validate_import(dataset);row=observation(dataset,observation_id)
    expected={'audio','transcript','alignment','mora_analysis','acoustic_evidence'}
    if set(sources)!=expected:raise ValueError('ANALYSIS_SOURCE_SET_INVALID')
    refs={k:artifact(v,Path(dataset.source).parent) for k,v in sources.items()}
    for key,original in [('audio','audio_identity'),('transcript','transcript_source')]:
        declared=artifact(row[original],Path(dataset.source).parent)
        if refs[key]!=declared:raise ValueError('ANALYSIS_LEARNER_SOURCE_IDENTITY_MISMATCH')
    if dataset.data['material_kind']=='REAL_LEARNER_AUDIO':
        from speech_xray.corpus.audio_validation import inspect_audio
        _,_,reason=inspect_audio(refs['audio']['path'])
        if reason:raise ValueError(reason)
    mora,_=read_json(Path(refs['mora_analysis']['path']))
    selected=[s for s in mora['long_vowel_spans'] if s['id']==span_id]
    if len(selected)!=1:raise ValueError('LEARNER_TARGET_NOT_MAPPED')
    s=selected[0];word=next(w for w in mora['words'] if w['index']==s['word_index'])
    indices=[next(m['word_mora_index'] for m in mora['morae'] if m['index']==i) for i in s['mora_indices']]
    linguistic={'target_id':row['target']['target_id'] if row['target'] else observation_id+':target',
        'target_surface':word['surface'],'target_reading':word['reading'],'target_mora_span':s['mora_span'],
        'target_vowel_class':s['vowel_class'],'word_mora_indices':indices,'mapping_basis':s['mapping_basis'],
        'lexical_identity':word['surface']}
    if row['target'] is not None and signature(row['target'])!=signature(linguistic):
        raise ValueError('DECLARED_TARGET_ANALYSIS_MISMATCH')
    target=TargetIdentity(linguistic['target_id'],int(s['word_index']),tuple(map(int,indices)),
                         s['phone_label'],s['vowel_class'],2,s['mapping_basis'])
    entry=ReferenceEntry(row['utterance_id'],target.target_id,row['speaker_id'],observation_id,
                         row['utterance_id'],span_id,tuple((k,ArtifactReference(**v)) for k,v in sorted(refs.items())))
    # Ephemeral validation context only, never a reference artifact/profile.
    # Its learner material kind is rejected by the unchanged native loader.
    context=ReferenceManifest('learner-validation:'+dataset.data['dataset_id'],row['utterance_id'],
        refs['transcript']['sha256'],target,(('material_kind','LEARNER_OBSERVATION'),),
        'Learner integrity context, not native reference', (entry,),dataset.source,dataset.sha256)
    validated=validate_entry(context,entry)
    decoded=load_audio(refs['audio']['path']).metadata
    acoustic,_=read_json(Path(refs['acoustic_evidence']['path']));audio=acoustic['audio']
    if (decoded.sha256,decoded.sample_rate_hz,decoded.frame_count,decoded.channels)!=(
            refs['audio']['sha256'],audio['sample_rate_hz'],audio['frame_count'],audio['channels']):
        raise ValueError('LEARNER_DECODED_AUDIO_DOMAIN_MISMATCH')
    rate=measure_utterance_rate(validated.alignment,validated.mora_count)
    return LearnerAnalysis(dataset,observation_id,serialize(refs),span_id,serialize(linguistic),
                           validated.span,rate,normalize_duration(validated.span,rate))


def plan_analysis(dataset, observation_id, output_root, acoustic_config=AcousticConfig()):
    results={r['observation_id']:r for r in validate_import(dataset)}
    row=observation(dataset,observation_id)
    if results[observation_id]['status']!='IMPORTED':return results[observation_id]
    # Real sources pass the same technical intake, never a pronunciation check.
    from speech_xray.corpus.audio_validation import inspect_audio
    if dataset.data['material_kind']=='REAL_LEARNER_AUDIO':
        _,_,reason=inspect_audio(artifact(row['audio_identity'],Path(dataset.source).parent)['path'])
        if reason:return {'observation_id':observation_id,'status':'ABSTAIN_UNSUPPORTED_EXTERNAL_SAMPLE'
            if dataset.data['source_type']=='EXTERNAL_LEARNER_CORPUS' else 'ABSTAIN_INVALID_CONTROLLED_SAMPLE',
            'reason_codes':[reason]}
    config=pipeline_configuration(acoustic_config,run_label='learner-evaluation')
    from .serialization import ROOT
    code={p.name:digest(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
    signature_hash=identity({'dataset':dataset.identity,'observation':row,'configuration':config,'evaluation_code':code})
    folder=private_path(output_root)/signature_hash/identifier(observation_id)
    return {'status':'PLANNED','dataset_role':'LEARNER','evaluation_run_id':dataset.data['evaluation_run_id'],
        'observation_id':observation_id,'dataset_identity':dataset.identity,'source_type':dataset.data['source_type'],
        'input_signature':signature_hash,'configuration':config,'evaluation_code_identity':code,'run_directory':str(folder),
        'stages':['EXISTING_MFA_CPU','EXISTING_MORA_MAPPING','EXISTING_ACOUSTICS',
                  'EXISTING_INTEGRITY','EXISTING_NORMALIZATION','LINGUISTIC_TARGET_COMPATIBILITY','TASK010_DURATION_FORMULAS'],
        'native_reference_export_allowed':False,'dry_run':True}


def analyse_learner(dataset, observation_id, output_root, execute=False, aligner=None, reading_provider=None, extractor=None,
                   acoustic_config=AcousticConfig()):
    if execute and dataset.data['material_kind']=='REAL_LEARNER_AUDIO' and any(
            callback is not None for callback in (aligner,reading_provider,extractor)):
        raise ValueError('REAL_LEARNER_PIPELINE_REQUIRES_ACCEPTED_ADAPTERS')
    plan=plan_analysis(dataset,observation_id,output_root,acoustic_config)
    if not execute or plan['status']!='PLANNED':return plan
    folder=private_path(plan['run_directory']);receipt=folder/'analysis-receipt.json'
    if receipt.exists():
        previous,_=read_json(receipt)
        if previous['input_signature']!=plan['input_signature']:raise ValueError('ANALYSIS_RECEIPT_CONTEXT_CHANGED')
        for ref in previous['sources'].values():artifact(ref,folder)
        for selected in previous['analyses']:
            load_analysis(dataset,observation_id,previous['sources'],selected['span_id'])
        return previous
    row=observation(dataset,observation_id)
    stage='ALIGNMENT_FAILED'
    try:
        folder.mkdir(parents=True,exist_ok=False);(folder/'input').mkdir()
        stem=identifier(observation_id)
        paths={'run_directory':str(folder),'prepared_audio':str(folder/'input'/(stem+'.wav')),
            'transcript':str(folder/'input'/(stem+'.lab')),'textgrid':str(folder/'aligned'/(stem+'.TextGrid'))}
        original=artifact(row['audio_identity'],Path(dataset.source).parent)
        shutil.copyfile(original['path'],paths['prepared_audio'])
        if digest(paths['prepared_audio'])!=original['sha256']:raise ValueError('PREPARED_AUDIO_CHANGED')
        Path(paths['transcript']).write_bytes((row['transcript']+'\n').encode('utf-8'))
        from types import SimpleNamespace
        (aligner or mfa_align)(paths,SimpleNamespace(audio_path=original['path']))
        from speech_xray.alignment.textgrid_parser import parse_textgrid
        alignment=parse_textgrid(Path(paths['textgrid']));alignment_ref=save(folder/'alignment.json',alignment.to_dict())
        stage='MORA_MAPPING_FAILED'
        from speech_xray.japanese.long_vowel_mapper import analyze_mora
        from speech_xray.japanese.reading import SudachiReadingProvider
        mora=analyze_mora(alignment,reading_provider or SudachiReadingProvider())
        mora_ref=save(folder/'mora-analysis.json',mora.to_dict())
        stage='ACOUSTIC_EXTRACTION_FAILED'
        from speech_xray.acoustics.mora_input import load_mora_analysis
        from speech_xray.acoustics.pipeline import extract_acoustic_evidence
        acoustic=(extractor or extract_acoustic_evidence)(original['path'],load_mora_analysis(mora_ref.path),acoustic_config)
        if acoustic.config.to_dict()!=plan['configuration']['acoustics']:
            raise ValueError('EXTRACTION_CONFIG_DIFFERS_FROM_LEARNER_PLAN')
        acoustic_ref=save(folder/'acoustic-evidence.json',acoustic.to_dict())
        sources={'audio':original,'transcript':artifact(row['transcript_source'],Path(dataset.source).parent),
            'alignment':asdict(alignment_ref),'mora_analysis':asdict(mora_ref),'acoustic_evidence':asdict(acoustic_ref)}
        stage='LEARNER_INTEGRITY_FAILED';analyses=[];abstentions=[]
        for span in mora.long_vowel_spans:
            try:
                item=load_analysis(dataset,observation_id,sources,span.id)
                analyses.append({'span_id':span.id,'target':decode(item.target_json),
                                 'duration':asdict(item.duration)})
            except ValueError as error:abstentions.append({'span_id':span.id,'reason':str(error)})
        result={'schema_version':'0.1','status':'ANALYSED' if analyses else (
            'ABSTAIN_UNSUPPORTED_EXTERNAL_SAMPLE' if dataset.data['source_type']=='EXTERNAL_LEARNER_CORPUS'
            else 'ABSTAIN_UNRESOLVED_TARGET'),
            'observation_id':observation_id,'input_signature':plan['input_signature'],
            'configuration':plan['configuration'],'dataset_identity':dataset.identity,'dataset_role':'LEARNER',
            'sources':sources,'analyses':analyses,'target_abstentions':abstentions,
            'unresolved_items':[x.to_dict() for x in mora.unresolved_items]}
        save(receipt,result);return result
    except (OSError,ValueError,RuntimeError) as error:
        result={'status':stage,'observation_id':observation_id,'reason_codes':[str(error)],'dataset_role':'LEARNER'}
        if folder.is_dir():save(folder/'failure-report.json',result)
        return result
