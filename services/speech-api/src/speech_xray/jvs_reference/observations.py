"""Private utterance intake; all linguistic/acoustic/reference math is upstream."""

from pathlib import Path
from dataclasses import replace
from speech_xray.alignment.textgrid_parser import parse_textgrid
from speech_xray.japanese.long_vowel_mapper import analyze_mora
from speech_xray.japanese.reading import SudachiReadingProvider
from speech_xray.acoustics.mora_input import load_mora_analysis
from speech_xray.acoustics.pipeline import extract_acoustic_evidence
from speech_xray.acoustics.models import evidence_json
from speech_xray.corpus.batch_plan import digest, object_hash, pipeline_configuration
from speech_xray.corpus.pipeline import new_text
from speech_xray.external_jvs.smoke import aligned_word_identity
from speech_xray.reference.models import ArtifactReference, ReferenceEntry, ReferenceManifest, TargetIdentity
from speech_xray.reference.integrity import validate_entry, IntegrityError
from speech_xray.reference.speech_rate import measure_utterance_rate
from speech_xray.reference.normalization import normalize_duration
from .cache import safe_directory, read_control, validate_artifacts


def utterance(job, aligned, root, smoke=None):
    """Reuse only a complete verified receipt, or retain an immutable new attempt."""
    if not Path(job['audio_path']).is_file():
        return {'status': 'AUDIO_MISSING'}
    if digest(job['audio_path']) != job['audio_sha256']:
        return {'status': 'AUDIO_IDENTITY_MISMATCH'}
    if aligned['status'] != 'PASS':
        return {'status': 'ALIGNMENT_FAILED', 'reason': aligned.get('reason')}
    grid = safe_directory(aligned['textgrid'])
    lab = safe_directory(aligned['transcript'])
    signature = object_hash({'audio':job['audio_sha256'], 'text':digest(lab), 'grid':digest(grid),
        'pipeline':pipeline_configuration(), 'adapter':digest(Path(__file__)),
        'speaker':job['speaker_id'], 'prompt':job['prompt_id']})
    parent = safe_directory(root) / signature
    parent.mkdir(parents=True, exist_ok=True)
    for previous in sorted(parent.glob('attempt-*/receipt.json')):
        try:
            value, _ = read_control(previous)
            validate_artifacts(value, signature)
            return {**value, 'execution_cache_hit':True}
        except (OSError, ValueError, KeyError, TypeError):
            pass
    number = 0
    while (parent / f'attempt-{number:03}').exists():number += 1
    folder = parent / f'attempt-{number:03}';folder.mkdir()
    refs = {'audio':job['audio_path'], 'transcript':str(lab), 'textgrid':str(grid)}
    stage = 'MORA_MAPPING_FAILED'
    reused = False
    try:
        alignment = parse_textgrid(grid)
        if smoke is not None:
            original = Path(smoke['outputs']['run_directory'])
            refs.update(alignment=str(original/'alignment.json'), mora_analysis=str(original/'mora-analysis.json'),
                acoustic_evidence=str(original/'acoustic-evidence.json'))
            for name in ('alignment.json','mora-analysis.json','acoustic-evidence.json'):
                if digest(original/name) != smoke['derived_sha256'][name]:raise ValueError('ACCEPTED_SMOKE_CHANGED')
            reused = True
        else:
            new_text(folder/'alignment.json',alignment.to_json())
            analysis = analyze_mora(alignment,SudachiReadingProvider())
            new_text(folder/'mora-analysis.json',analysis.to_json())
            refs.update(alignment=str(folder/'alignment.json'),mora_analysis=str(folder/'mora-analysis.json'))
            stage = 'ACOUSTIC_EXTRACTION_FAILED'
            acoustic = extract_acoustic_evidence(Path(job['audio_path']),load_mora_analysis(folder/'mora-analysis.json'))
            new_text(folder/'acoustic-evidence.json',acoustic.to_json())
            refs['acoustic_evidence']=str(folder/'acoustic-evidence.json')
        value={'status':'PASS','signature':signature,'accepted_smoke_reused':reused,
            'artifacts':{k:{'path':str(safe_directory(v)),'sha256':digest(v)} for k,v in sorted(refs.items())}}
    except (OSError,ValueError,RuntimeError) as error:
        value={'status':stage,'reason':str(error),'signature':signature,'accepted_smoke_reused':False,
            'artifacts':{k:{'path':str(safe_directory(v)),'sha256':digest(v)} for k,v in sorted(refs.items()) if Path(v).is_file()}}
    new_text(folder/'receipt.json',evidence_json(value))
    return {**value,'execution_cache_hit':False}


def map_target(target, prompt, analysis):
    index, reason = aligned_word_identity(target,prompt['words'],analysis.words)
    if index is not None and analysis.words[index].reading_result.reading != target['expected_word_reading']:
        return None,'ALIGNED_WORD_READING_DIFFERS'
    spans=[s for s in analysis.long_vowel_spans if s.word_index==index
        and tuple(analysis.morae[i].word_mora_index for i in s.mora_indices)==tuple(target['word_mora_indices'])
        and s.mapping_basis==target['candidate_type'] and s.vowel_class==target['vowel_class']
        and analysis.words[s.word_index].surface==target['surface_hint']]
    return (spans[0],None) if len(spans)==1 else (None,reason or 'DECLARED_LEXICAL_TARGET_NOT_UNIQUELY_MAPPED')


def admit(target, prompt, job, bundle, identity=None):
    row={'speaker_id':job['speaker_id'],'prompt_id':job['prompt_id'],'target_id':target['target_id'],
         'audio_sha256':job['audio_sha256'],'alignment_success':bundle['status'] not in {'AUDIO_MISSING','ALIGNMENT_FAILED','AUDIO_IDENTITY_MISMATCH'},
         'mapping_success':False,'acoustic_success':False,'normalization_success':False}
    if bundle['status'] != 'PASS':return {**row,'status':bundle['status'],'reason':bundle.get('reason')},None,identity
    from types import SimpleNamespace
    refs=bundle['artifacts']
    saved, _ = read_control(refs['mora_analysis']['path'])
    mapped = load_mora_analysis(refs['mora_analysis']['path'])
    analysis=SimpleNamespace(words=tuple(SimpleNamespace(surface=w['surface'],
        reading_result=SimpleNamespace(reading=w['reading'])) for w in saved['words']),
        morae=tuple(SimpleNamespace(word_mora_index=m['word_mora_index']) for m in saved['morae']),
        long_vowel_spans=mapped.long_vowel_spans)
    span,reason=map_target(target,prompt,analysis)
    if span is None:return {**row,'status':'TARGET_NOT_MAPPED','reason':reason},None,identity
    row['mapping_success']=True
    proposed=TargetIdentity(target['target_id'],span.word_index,tuple(target['word_mora_indices']),
        span.phone_label,span.vowel_class,2,span.mapping_basis)
    identity=identity or proposed
    entry=ReferenceEntry(job['prompt_id'],target['target_id'],job['speaker_id'],'parallel100',
        job['speaker_id']+'__'+job['prompt_id'],span.id,
        tuple((k,ArtifactReference(**refs[k])) for k in ('audio','alignment','mora_analysis','acoustic_evidence','transcript')))
    manifest=ReferenceManifest('task008-'+target['target_id'],job['prompt_id'],refs['transcript']['sha256'],identity,
        tuple(sorted({'name':'JVS parallel100','source':'EXTERNAL_RESEARCH_CORPUS','local_only':True,
        'usage_restrictions':'Private research evidence; derived publication rights not reviewed',
        'material_kind':'REAL_REFERENCE_AUDIO'}.items())),'TASK-008', (entry,), '', '')
    try:
        source=validate_entry(manifest,entry)
        row['acoustic_success']=True
        rate=measure_utterance_rate(source.alignment,source.mora_count)
        duration=normalize_duration(source.span,rate)
        row.update(status='VALID',normalization_success=True,original_span=span.to_dict(),
            rate_context=rate.to_dict(),raw_duration_ms=duration.raw_duration_ms,
            rate_normalized_duration=duration.rate_normalized_duration,
            rate_normalized_duration_per_mora=duration.rate_normalized_duration_per_mora,
            sources=entry.to_dict()['sources'])
        return row,entry,identity
    except (IntegrityError,ValueError) as error:
        # Linguistic rate coverage can fail even with valid target acoustic evidence.
        if isinstance(error,IntegrityError) and str(error)=='INCOMPLETE_LINGUISTIC_RATE_COVERAGE':row['acoustic_success']=True
        return {**row,'status':getattr(error,'status','INVALID_UTTERANCE_RATE'),'reason':str(error)},None,identity
