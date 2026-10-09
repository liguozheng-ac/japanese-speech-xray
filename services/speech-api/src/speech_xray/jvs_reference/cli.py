"""Local staged corpus build; CPU workers are isolated by actual speaker batch."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import subprocess
import sys
from .lineage import load_inputs
from .cache import read_control,safe_directory
from .mfa_batch import align_batch,validated_batch_receipt,batch_signature
from .observations import utterance
from .build import build_targets,save_verified
from speech_xray.corpus.validation import PROJECT_ROOT
from speech_xray.corpus.batch_plan import pipeline_configuration,digest


def accepted_alignments(data, root):
    aligned={};smokes={}
    for s in data['smoke']['outcomes']:
        if s['alignment_status']=='PASS':
            key=(s['speaker_id'],s['corpus_prompt_id'])
            aligned[key]={'status':'PASS','textgrid':s['outputs']['textgrid'],'transcript':s['outputs']['transcript']}
            smokes[key]=s
    for p in sorted((root/'qualification-batches').glob('*.json')):
        value,_=read_control(p)
        number=int(value['speaker_id'][3:])-1
        work,_=read_control(root/'qualification-worklists'/f'worker-{number:02}.json')
        jobs=work[value['speaker_id']]
        signature,_=batch_signature(sorted(jobs,key=lambda j:j['prompt_id']))
        value=validated_batch_receipt(p,jobs,signature)
        for prompt,result in value['results'].items():aligned[(value['speaker_id'],prompt)]=result
    return aligned,smokes


def analyze_speaker(jobs, root, worker, aligned, smokes):
    missing=[j for j in jobs if (j['speaker_id'],j['prompt_id']) not in aligned]
    batch=None
    if missing:
        batch=align_batch(missing,root/'alignment-batches/full',root/'workers'/f'full-worker-{worker:02}')
        for prompt,value in batch['results'].items():aligned[(missing[0]['speaker_id'],prompt)]=value
    bundles=[]
    for j in jobs:
        key=(j['speaker_id'],j['prompt_id'])
        value=utterance(j,aligned[key],root/'utterance-cache',smokes.get(key))
        bundles.append({'speaker_id':key[0],'prompt_id':key[1],
            'bundle':{k:v for k,v in value.items() if k!='execution_cache_hit'}})
    return bundles,batch


def main(argv=None):
    parser=argparse.ArgumentParser(description='Private JVS reference build; no learner diagnosis')
    parser.add_argument('--source-root',type=Path,default=PROJECT_ROOT/'data/private/external/jvs')
    parser.add_argument('--output-root',type=Path,default=PROJECT_ROOT/'data/private/external/jvs/reference-builds/task008-v1')
    parser.add_argument('--phase',choices=('qualification','full'),default='qualification')
    parser.add_argument('--workers',type=int,default=6)
    parser.add_argument('--worker',type=int)
    args=parser.parse_args(argv);root=safe_directory(args.output_root)
    if not 1<=args.workers<=8:raise ValueError('WORKERS_MUST_BE_1_TO_8')
    if args.worker is not None:
        work,_=read_control(root/'full-worklists'/f'worker-{args.worker:02}.json')
        for group in work:
            bundles,batch=analyze_speaker(group,root,args.worker,{}, {})
            save_verified(root/'full-bundles'/f"{group[0]['speaker_id']}.json",bundles)
            print(f"{group[0]['speaker_id']} utterances={len(group)} alignment_pass={sum(v['status']=='PASS' for v in batch['results'].values()) if batch else 0}",flush=True)
        return 0
    data=load_inputs(args.source_root)
    save_verified(root/'target-lineage.json',data['lineage'])
    targets=data['targets'];prompts={t['corpus_prompt_id'] for t in targets}
    official={p['corpus_prompt_id']:p for p in data['inventory']['prompts']}
    jobs=[{**r,'text':official[r['prompt_id']]['text'],'source_type':'EXTERNAL_RESEARCH_CORPUS'}
        for r in data['inventory']['records'] if r['prompt_id'] in prompts]
    aligned,smokes=accepted_alignments(data,root)
    qualification_jobs=[j for j in jobs if j['speaker_id'] in {f'jvs{i:03}' for i in range(1,6)}]
    bundles={}
    for speaker in sorted({j['speaker_id'] for j in qualification_jobs}):
        results,_=analyze_speaker([j for j in qualification_jobs if j['speaker_id']==speaker],root,0,aligned,smokes)
        for r in results:bundles[(r['speaker_id'],r['prompt_id'])]=r['bundle']
        print('qualification analysis '+speaker,flush=True)
    results,_=build_targets(data,qualification_jobs,bundles,root,'qualification')
    qualified={r['target_id']:r for r in results}
    print('qualified='+str(sum(r['qualification_status']=='QUALIFIED_FOR_FULL_BUILD' for r in results)),flush=True)
    if args.phase=='qualification':return 0
    full_prompts={r['prompt_id'] for r in results if r['qualification_status']=='QUALIFIED_FOR_FULL_BUILD'}
    full_jobs=[j for j in jobs if j['prompt_id'] in full_prompts]
    groups=[[j for j in full_jobs if j['speaker_id']==speaker] for speaker in sorted({j['speaker_id'] for j in full_jobs})
        if speaker not in {f'jvs{i:03}' for i in range(1,6)}]
    for worker in range(args.workers):save_verified(root/'full-worklists'/f'worker-{worker:02}.json',groups[worker::args.workers])
    logroot=root/'full-worker-logs';logroot.mkdir(exist_ok=True)
    def run(worker):
        number=0
        while (logroot/f'worker-{worker:02}-run-{number:03}.txt').exists():number+=1
        env=dict(os.environ);env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
        with (logroot/f'worker-{worker:02}-run-{number:03}.txt').open('x',encoding='utf-8') as stream:
            return subprocess.run([sys.executable,str(PROJECT_ROOT/'scripts/build_jvs_references.py'),
                '--output-root',str(root),'--worker',str(worker)],env=env,cwd=PROJECT_ROOT,stdout=stream,stderr=subprocess.STDOUT).returncode
    with ThreadPoolExecutor(max_workers=args.workers) as pool:codes=list(pool.map(run,range(args.workers)))
    if any(codes):raise RuntimeError('PRIVATE_FULL_WORKER_FAILED:'+str(codes))
    for path in sorted((root/'full-bundles').glob('*.json')):
        value,_=read_control(path)
        for row in value:bundles[(row['speaker_id'],row['prompt_id'])]=row['bundle']
    # Validate every bundle again before reference intake, including completed workers.
    from .cache import validate_artifacts
    for bundle in bundles.values():
        if 'signature' in bundle:validate_artifacts(bundle,bundle['signature'])
    full,profiles=build_targets(data,full_jobs,bundles,root,'full',qualified)
    ready=sum(p.profile_status=='READY_FOR_EXPERIMENT' for p in profiles.values())
    save_verified(root/'build-manifest-v2.json',{'build_id':'TASK-008-v1','results_schema_version':'0.2','source_type':'EXTERNAL_RESEARCH_CORPUS',
        'lineage':data['lineage'],'configuration':pipeline_configuration(),'qualification':results,'full':full,
        'REFERENCE_DATA_READY_FOR_DIAGNOSIS_EXPERIMENT':ready>=2,'utterance_count':len(bundles),
        'primary_batch_adapter_sha256':digest(Path(__file__).with_name('mfa_batch.py')),
        'code_identity':{p.name:digest(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
        'original_deferred_targets':data['lineage']['deferred_target_ids'],
        'execution_policy':{'primary_mfa_batch_unit':'ONE_ACTUAL_SPEAKER',
            'full_worker_count':args.workers,'worker_thread_caps':{'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'},
            'parent_thread_environment':{k:os.environ.get(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')}},
        'no_outlier_removal':True,'minimum_independent_speakers':5})
    print(f'full_profiles={len(profiles)} ready={ready}',flush=True)
    return 0
