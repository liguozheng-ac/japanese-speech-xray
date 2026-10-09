"""Deterministic qualification, audited intake and existing ReferenceProfile output."""
from collections import Counter
from dataclasses import replace
from pathlib import Path
from speech_xray.acoustics.models import evidence_json
from speech_xray.corpus.batch_plan import digest, object_hash
from speech_xray.corpus.pipeline import new_text
from speech_xray.reference.models import ReferenceManifest
from speech_xray.reference.manifest import load_manifest
from speech_xray.reference.profile_builder import build_reference_profile
from .cache import safe_directory, read_control
from .observations import admit
from .stage_evidence import verify_job_sources,observed_stages


def save_verified(path, value):
    """Never overwrite a different canonical artifact on resume."""
    path=safe_directory(path);encoded=evidence_json(value)
    if path.exists():
        if path.read_text(encoding='utf-8') != encoded:raise ValueError('CANONICAL_OUTPUT_CHANGED:'+path.name)
    else:new_text(path,encoded)
    return {'path':str(path),'sha256':digest(path)}


def qualify(rows, minimum=5):
    ids=[r['speaker_id'] for r in rows]
    if len(set(ids))!=len(ids):raise ValueError('DUPLICATE_SPEAKER_OBSERVATION')
    valid=[r for r in rows if r['status']=='VALID']
    hashes=[r['audio_sha256'] for r in valid]
    if len(set(hashes))!=len(hashes):raise ValueError('DUPLICATE_AUDIO_OBSERVATION_NOT_INDEPENDENT')
    if len(valid)>=minimum:return 'QUALIFIED_FOR_FULL_BUILD'
    if not any(r['alignment_success'] for r in rows):return 'DEFERRED_ALIGNMENT_FAILURE'
    if not any(r['mapping_success'] for r in rows):return 'DEFERRED_MAPPING_FAILURE'
    return 'DEFERRED_INSUFFICIENT_VALID_OBSERVATIONS'


def counts(rows):
    return {'attempted_speakers':len(rows), 'alignment_success_speakers':sum(r['alignment_success'] for r in rows),
        'mapped_speakers':sum(r['mapping_success'] for r in rows),
        'acoustic_success_speakers':sum(r['acoustic_success'] for r in rows),
        'normalization_success_speakers':sum(r['normalization_success'] for r in rows),
        'acoustic_span_status_counts':dict(sorted(Counter(r.get('acoustic_span_status','NOT_RECORDED') for r in rows).items())),
        'valid_reference_observation_speakers':sum(r['status']=='VALID' for r in rows),
        'failure_reasons':dict(sorted(Counter(r.get('reason') or r['status'] for r in rows if r['status']!='VALID').items()))}


def build_targets(data, jobs, bundles, root, phase, qualification=None, *, build_id='task008'):
    # Keep initial execution artifacts for audit; v2 separates extractor success
    # from the later strict whole-bundle reference intake gate.
    root=safe_directory(root)/'results-v2'/phase
    prompts={p['corpus_prompt_id']:p for p in data['discovery']['targets_by_prompt']}
    audio={p['corpus_prompt_id']:p['available_speaker_count'] for p in data['inventory']['prompts']}
    reports=[];profiles={}
    for target in sorted(data['targets'],key=lambda t:t['target_id']):
        tid=target['target_id'];selected=[j for j in jobs if j['prompt_id']==target['corpus_prompt_id']]
        if phase=='full' and qualification[tid]['qualification_status']!='QUALIFIED_FOR_FULL_BUILD':continue
        rows=[];entries=[];identity=None
        for job in sorted(selected,key=lambda j:j['speaker_id']):
            bundle=bundles[(job['speaker_id'],job['prompt_id'])]
            try:
                verify_job_sources(job,bundle)
            except ValueError as error:
                bundle={**bundle,'status':'INTEGRITY_FAILURE','reason':str(error)}
            row,entry,identity=admit(target,prompts[job['prompt_id']],job,bundle,identity)
            row.update(observed_stages(target,prompts[job['prompt_id']],bundle))
            rows.append(row)
            if entry:entries.append(entry)
        state=qualify(rows)
        report={'target_id':tid,'prompt_id':target['corpus_prompt_id'],'orthographic_pattern':target['orthographic_pattern'],
            'vowel_class':target['vowel_class'],'candidate_type':target['candidate_type'],
            'audio_available_speakers':audio[target['corpus_prompt_id']],**counts(rows),
            'qualification_status':state,'attempted_speaker_ids':[r['speaker_id'] for r in rows]}
        report['observations_artifact']=save_verified(root/tid/'intake-ledger.json',rows)
        if identity:
            manifest={'schema_version':'0.1','reference_set_id':build_id+'-'+phase+'-'+tid,
                'prompt_id':target['corpus_prompt_id'],'transcript_sha256':next(iter(bundles[(j['speaker_id'],j['prompt_id'])]['artifacts']['transcript']['sha256']
                    for j in selected if bundles[(j['speaker_id'],j['prompt_id'])]['status']=='PASS')),
                'target':identity.to_dict(),'dataset':{'name':'JVS parallel100','source':'EXTERNAL_RESEARCH_CORPUS',
                'local_only':True,'usage_restrictions':'Private research evidence; derived publication rights not reviewed','material_kind':'REAL_REFERENCE_AUDIO'},
                'creation_metadata':{'label':('TASK-008' if build_id=='task008' else build_id)+' '+phase},
                'entries':[e.to_dict() for e in entries]}
            report['manifest_artifact']=save_verified(root/tid/'reference-manifest.json',manifest)
            profile=build_reference_profile(load_manifest(report['manifest_artifact']['path']))
            if profile.rejected:raise ValueError('VALIDATED_INTAKE_REJECTED_BY_REFERENCE_BUILDER')
            sanity(profile)
            report['readiness']=str(profile.profile_status)
            report['profile_artifact']=save_verified(root/tid/'reference-profile.json',profile.to_dict())
            profiles[tid]=profile
        else:report['readiness']='NO_VALID_OBSERVATIONS'
        reports.append(report)
    save_verified(root/'target-results.json',reports)
    return reports,profiles


def sanity(profile):
    ids=[s.speaker_id for s in profile.speakers]
    hashes=[dict(s.takes[0].entry.sources)['audio'].sha256 for s in profile.speakers]
    if len(set(ids))!=len(ids) or len(set(hashes))!=len(hashes):raise ValueError('INDEPENDENCE_CHECK_FAILED')
    for _,stat in profile.statistics:
        if stat.count != len(ids):raise ValueError('STATISTICS_COUNT_MISMATCH')
        if stat.count and not (all(v.is_finite() for v in (stat.minimum,stat.q25,stat.median,stat.q75,stat.maximum,stat.mad,stat.iqr))
            and stat.minimum<=stat.q25<=stat.median<=stat.q75<=stat.maximum and stat.mad>=0 and stat.iqr>=0):
            raise ValueError('DISTRIBUTION_SANITY_FAILED')
