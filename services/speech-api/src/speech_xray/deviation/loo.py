"""Private native-reference self-consistency experiment; no learner labels."""
from pathlib import Path
import hashlib
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from collections import Counter

from speech_xray.corpus.batch_plan import digest
from speech_xray.corpus.validation import PROJECT_ROOT
from speech_xray.reference.json_input import read_json
from speech_xray.reference.models import ArtifactReference
from speech_xray.reference.robust_stats import summarize
from speech_xray.jvs_reference.cache import safe_directory
from .snapshot import VerifiedReferenceSnapshot
from .engine import compare_duration
from .models import EvidenceStatus
from .serialization import save_canonical


def target_experiment(manifest_path, profile_artifact, output, version='task009-v2'):
    output = safe_directory(output)
    snapshot = VerifiedReferenceSnapshot(manifest_path,profile_artifact,version)
    rows = []
    for speaker in snapshot.profile.speakers:
        slot = hashlib.sha256(speaker.speaker_id.encode('utf-8')).hexdigest()[:20]
        folder = output/'cases'/slot
        reference = snapshot.build_excluding(speaker.speaker_id,folder)
        snapshot.assert_exclusion(speaker.speaker_id,reference.profile)
        result = compare_duration(snapshot.candidate(speaker.speaker_id),reference)
        if result.status != EvidenceStatus.OK:
            raise ValueError('LOO_COMPARISON_ABSTAINED:'+':'.join(result.reason_codes))
        if speaker.speaker_id in result.reference['speaker_ids']:
            raise ValueError('LOO_CANDIDATE_INCLUDED_IN_RESULT_REFERENCE')
        artifact = save_canonical(folder/'deviation-evidence.json',result.to_dict())
        rows.append({'speaker_id':speaker.speaker_id,'reference_n':len(reference.profile.speakers),
                     'reference_speaker_ids':result.reference['speaker_ids'],
                     'artifact':{'path':artifact.path,'sha256':artifact.sha256},
                     'primary_evidence':result.evidence['features']['rate_normalized_duration']})
        if len(rows)%20 == 0:
            print(snapshot.manifest.target.target_id,'comparisons',len(rows),flush=True)
    snapshot.verify_hashes()
    primary = [r['primary_evidence'] for r in rows]
    stats = {field:summarize(e[field] for e in primary if e[field] is not None).to_dict()
             for field in ('signed_delta','ratio_to_median','mad_distance')}
    summary = {'target_id':snapshot.manifest.target.target_id,
               'experiment':'NATIVE_REFERENCE_SELF_CONSISTENCY_LEAVE_ONE_SPEAKER_OUT',
               'source_n':len(snapshot.profile.speakers),'comparison_count':len(rows),
               'reference_n_counts':dict(sorted(Counter(str(r['reference_n']) for r in rows).items())),
               'self_leakage_count':sum(r['speaker_id'] in r['reference_speaker_ids'] for r in rows),
               'primary_feature':'rate_normalized_duration','feature_distributions':stats,
               'direction_counts':dict(sorted(Counter(e['direction'] for e in primary).items())),
               'inside_iqr':sum(e['inside_iqr'] for e in primary),
               'outside_iqr':sum(not e['inside_iqr'] for e in primary),
               'inside_observed_min_max':sum(e['inside_observed_min_max'] for e in primary),
               'outside_observed_min_max':sum(not e['inside_observed_min_max'] for e in primary),
               'mad_distance_status_counts':dict(sorted(Counter(e['mad_distance_status'] for e in primary).items())),
               'original_builder_code_object_reused':snapshot.builder.__code__ is __import__(
                   'speech_xray.reference.profile_builder',fromlist=['build_reference_profile']).build_reference_profile.__code__,
               'validated_source_entry_count':len(snapshot._inputs),
               'source_profile_artifact':{'path':profile_artifact.path,'sha256':profile_artifact.sha256}}
    save_canonical(output/'comparisons.json',rows)
    save_canonical(output/'summary.json',summary)
    return summary


def _accepted_source(reference_root):
    manifest,identity = read_json(reference_root/'build-manifest.json')
    gate,_ = read_json(reference_root/'integrity-gate.json')
    if (manifest['build_id'] != 'task009-v2' or gate['REFERENCE_INTEGRITY_READY_FOR_DIAGNOSIS'] is not True
            or identity != gate['build_manifest_sha256']):
        raise ValueError('ACCEPTED_V2_REFERENCE_REQUIRED')
    return manifest,identity


def run_target(reference_root,output,index):
    reference_root,output=safe_directory(reference_root),safe_directory(output)
    manifest,_=_accepted_source(reference_root)
    if type(index) is not int or not 0 <= index < len(manifest['full']):
        raise ValueError('TARGET_INDEX_INVALID')
    row=manifest['full'][index]
    ref=row['manifest_artifact']
    if digest(ref['path']) != ref['sha256']:
        raise ValueError('SOURCE_REFERENCE_MANIFEST_CHANGED')
    target=hashlib.sha256(row['target_id'].encode('utf-8')).hexdigest()[:20]
    return target_experiment(ref['path'],ArtifactReference(**row['profile_artifact']),output/'targets'/target)


def run_experiment(reference_root, output, workers=5):
    reference_root,output = safe_directory(reference_root),safe_directory(output)
    if output == reference_root or output.is_relative_to(reference_root) or reference_root.is_relative_to(output):
        raise ValueError('EXPERIMENT_REQUIRES_SEPARATE_PRIVATE_ROOT')
    if type(workers) is not int or not 1 <= workers <= 5:
        raise ValueError('WORKER_COUNT_MUST_BE_ONE_TO_FIVE')
    manifest,identity = _accepted_source(reference_root)
    code_identity={p.name:digest(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
    if workers == 1:
        summaries=[run_target(reference_root,output,i) for i in range(len(manifest['full']))]
    else:
        logs=output/'worker-logs';logs.mkdir(parents=True,exist_ok=True)
        def worker(index):
            number=0
            while (logs/f'target-{index:02}-run-{number:03}.txt').exists():number+=1
            env=dict(os.environ);env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
            with (logs/f'target-{index:02}-run-{number:03}.txt').open('x',encoding='utf-8') as stream:
                code=subprocess.run([sys.executable,str(PROJECT_ROOT/'scripts/run_duration_loo.py'),
                    '--reference-root',str(reference_root),'--output-root',str(output),'--target-index',str(index)],
                    cwd=PROJECT_ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT).returncode
            if code:raise ValueError('LOO_TARGET_WORKER_FAILED:'+str(index))
            target=hashlib.sha256(manifest['full'][index]['target_id'].encode('utf-8')).hexdigest()[:20]
            return read_json(output/'targets'/target/'summary.json')[0]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            summaries=list(pool.map(worker,range(len(manifest['full']))))
    if code_identity != {p.name:digest(p) for p in sorted(Path(__file__).parent.glob('*.py'))}:
        raise ValueError('DEVIATION_CODE_CHANGED_DURING_EXPERIMENT')
    result = {'experiment_id':'task010-loo-v1','reference_version':'task009-v2',
              'experiment':'NATIVE_REFERENCE_SELF_CONSISTENCY_LEAVE_ONE_SPEAKER_OUT',
              'source_build_manifest_sha256':identity,'targets':summaries,
              'comparison_count':sum(r['comparison_count'] for r in summaries),
              'self_leakage_count':sum(r['self_leakage_count'] for r in summaries),
              'new_mfa_runs':0,'new_acoustic_extractions':0,
              'execution_policy':{'workers':workers,'child_threads':1},'code_identity':code_identity}
    save_canonical(output/'experiment-manifest.json',result)
    return result
