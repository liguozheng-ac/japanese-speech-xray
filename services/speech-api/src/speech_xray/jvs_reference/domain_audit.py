"""Read-only exact timing audit of privately retained alignment evidence."""
from pathlib import Path
import sys,json,re,wave,hashlib
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace
from speech_xray.jvs_reference.cache import read_control,validate_artifacts
from speech_xray.jvs_reference.observations import map_target
from speech_xray.jvs_reference.stage_evidence import verify_job_sources
from speech_xray.japanese.alignment_input import load_alignment
from speech_xray.acoustics.mora_input import load_mora_analysis
from speech_xray.acoustics.audio import load_audio
from speech_xray.acoustics.models import evidence_json
from speech_xray.reference.json_input import read_json
from speech_xray.reference.numeric import decimal_ratio
from speech_xray.reference.robust_stats import _quantile

from speech_xray.corpus.validation import PROJECT_ROOT
from .reconciliation import ensure_separate_roots
from .cache import safe_directory


def audit_build(source, previous, output):
    root=PROJECT_ROOT
    old,new=ensure_separate_roots(previous,output)
    source=safe_directory(source)
    if not (new/'v1-file-snapshot.json').is_file():raise ValueError('V1_FREEZE_REQUIRED')
    frozen,_=read_control(new/'v1-file-snapshot.json')
    pinned={r['path']:r['sha256'] for r in frozen}
    previous_manifest=old/'build-manifest-v2.json'
    if hashlib.sha256(previous_manifest.read_bytes()).hexdigest()!=pinned['build-manifest-v2.json']:
        raise ValueError('FROZEN_BUILD_MANIFEST_CHANGED')
    accepted,_=read_control(previous_manifest)
    audit,_=read_control(source/'reports/full-audit-v1.json')
    smoke,_=read_control(source/'reports/full-smoke-v2.json')
    if (hashlib.sha256((source/'reports/full-audit-v1.json').read_bytes()).hexdigest()!=accepted['lineage']['source_artifacts']['audit']
            or hashlib.sha256((source/'reports/full-smoke-v2.json').read_bytes()).hexdigest()!=accepted['lineage']['source_artifacts']['smoke']):
        raise ValueError('ACCEPTED_SOURCE_IDENTITY_CHANGED')
    targets=smoke['reviewed_recommendation']['selected_targets']
    prompts={p['corpus_prompt_id']:p for p in audit['discovery']['targets_by_prompt']}
    official={p['corpus_prompt_id']:p for p in audit['inventory']['prompts']}
    jobs={(j['speaker_id'],j['prompt_id']):{**j,'text':official[j['prompt_id']]['text']} for j in audit['inventory']['records']}
    def inside(a,b,end):return 0<=Fraction(a)<Fraction(b)<=end
    records=[];deltas=[];round_matches=0
    for p in sorted((old/'utterance-cache').glob('*/attempt-*/receipt.json')):
        if hashlib.sha256(p.read_bytes()).hexdigest()!=pinned[p.relative_to(old).as_posix()]:
            raise ValueError('FROZEN_RECEIPT_CHANGED')
        bundle,_=read_control(p);validate_artifacts(bundle,bundle['signature']);refs=bundle['artifacts']
        audio=Path(refs['audio']['path']);speaker=audio.parents[2].name;prompt=audio.stem;job=jobs[(speaker,prompt)]
        verify_job_sources(job,bundle)
        meta=load_audio(audio).metadata
        with wave.open(str(audio)) as w:assert (w.getnframes(),w.getframerate(),w.getnchannels())==(meta.frame_count,meta.sample_rate_hz,meta.channels)
        exact=Fraction(meta.frame_count*1000,meta.sample_rate_hz);alignment=load_alignment(refs['alignment']['path'])
        rawgrid=Path(refs['textgrid']['path']).read_text(encoding='utf-8-sig')
        xmax=Decimal(re.search(r'^xmax\s*=\s*(\S+)',rawgrid,re.M).group(1));assert Fraction(xmax)*1000==Fraction(alignment.end_ms)
        predicted=Decimal(str(round(meta.frame_count/meta.sample_rate_hz,6)))*1000
        matches=predicted==alignment.end_ms;round_matches+=matches
        nonempty=[w for w in alignment.words if w.label.strip()];last=nonempty[-1]
        core_ok=bool(nonempty) and all(inside(w.start_ms,w.end_ms,exact) for w in nonempty)
        saved,_=read_control(refs['mora_analysis']['path']);mapped=load_mora_analysis(refs['mora_analysis']['path'])
        view=SimpleNamespace(words=tuple(SimpleNamespace(surface=w['surface'],reading_result=SimpleNamespace(reading=w['reading'])) for w in saved['words']),morae=tuple(SimpleNamespace(word_mora_index=m['word_mora_index']) for m in saved['morae']),long_vowel_spans=mapped.long_vowel_spans)
        ac,_=read_json(Path(refs['acoustic_evidence']['path']));targetrows=[]
        for target in targets:
            if target['corpus_prompt_id']!=prompt:continue
            span,reason=map_target(target,prompts[prompt],view);assert span is not None,reason
            targetrows.append({'target_id':target['target_id'],'target_phone_start_ms':str(span.start_ms),'target_phone_end_ms':str(span.end_ms),'target_end_minus_wav_end_ms':str(Fraction(span.end_ms)-exact),'target_inside':inside(span.start_ms,span.end_ms,exact)})
        delta=Fraction(alignment.end_ms)-exact
        if delta>0:deltas.append(delta)
        records.append({'speaker_id':speaker,'prompt_id':prompt,'audio_sha256':refs['audio']['sha256'],'receipt':str(p),'receipt_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'wav_duration_exact_ms':str(exact),'sample_rate':meta.sample_rate_hz,'sample_count':meta.frame_count,'sample_period_ms':str(Fraction(1000,meta.sample_rate_hz)),'alignment_global_start_ms':str(alignment.start_ms),'alignment_global_end_ms':str(alignment.end_ms),'global_end_minus_wav_end_ms':str(delta),'textgrid_xmax_seconds':str(xmax),'matches_mfa_six_decimal_export':matches,'last_nonempty_word_start_ms':str(last.start_ms),'last_nonempty_word_end_ms':str(last.end_ms),'last_word_end_minus_wav_end_ms':str(Fraction(last.end_ms)-exact),'all_required_core_words_inside':core_ok,'required_core_words':[{'start_ms':str(w.start_ms),'end_ms':str(w.end_ms)} for w in nonempty],'analysis_config':ac['extraction_config'],'targets':targetrows})
        if len(records)%100==0:print('audited',len(records),flush=True)
        records[-1]['only_empty_intervals_cross_wav_end']=all(not i.label.strip() for i in alignment.words+alignment.phones if Fraction(i.end_ms)>exact)
    ordered=sorted(deltas);median=_quantile(ordered,Fraction(1,2)) if ordered else Fraction(0)
    stat={'min':ordered[0] if ordered else Fraction(0),'median':median,'MAD':(_quantile(sorted(abs(v-median) for v in ordered),Fraction(1,2)) if ordered else Fraction(0)),'q25':(_quantile(ordered,Fraction(1,4)) if ordered else Fraction(0)),'q75':(_quantile(ordered,Fraction(3,4)) if ordered else Fraction(0)),'max':ordered[-1] if ordered else Fraction(0)}
    affected=[r for r in records if Fraction(r['global_end_minus_wav_end_ms'])>0]
    from collections import Counter
    summary={'utterances':len(records),'affected':len(affected),'affected_target_observations':sum(len(r['targets']) for r in affected),'affected_targets_inside':sum(t['target_inside'] for r in affected for t in r['targets']),'affected_core_observations_inside':sum(len(r['targets']) for r in affected if r['all_required_core_words_inside']),'genuine_invalid_utterances':sum(not r['all_required_core_words_inside'] or not all(t['target_inside'] for t in r['targets']) for r in records),'mfa_export_round_matches':round_matches,'overrun_exact_ms':{k:str(v) for k,v in stat.items()},'overrun_display_ms':{k:str(decimal_ratio(v)) for k,v in stat.items()},'observed_magnitude_buckets_ms':dict(sorted(Counter(str(d) for d in deltas).items())),'readers_agree':True,'parser_exact':True}
    mfa_source=root/'.envs/mfa/Lib/site-packages/montreal_forced_aligner/textgrid.py'
    if 'duration = round(duration, 6)' not in mfa_source.read_text(encoding='utf-8'):
        raise ValueError('MFA_EXPORT_ROUNDING_SOURCE_CHANGED')
    result={'summary':summary,'utterances':records,'mfa_export_source_sha256':hashlib.sha256(mfa_source.read_bytes()).hexdigest()}
    out=new/'timing-audit-v2.json';encoded=evidence_json(result)
    if out.exists():assert out.read_text(encoding='utf-8')==encoded
    else:out.write_text(encoded,encoding='utf-8')
    print(json.dumps(summary),flush=True)
    return result
