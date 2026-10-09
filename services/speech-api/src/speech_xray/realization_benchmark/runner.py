"""Resumable locked-MFA execution, with identical per-target speaker batches."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import os
import shutil
import sqlite3
import subprocess
from speech_xray.corpus.validation import PROJECT_ROOT as R
from speech_xray.corpus.batch_plan import digest
from speech_xray.acoustics.models import evidence_json
from .artifacts import private, load, save, verify, pin
from .plan import code_pins


def database_evidence(folder, word):
    dbs = list((folder / 'mfa-temp').rglob('input.db'))
    if len(dbs) != 1: return {'database_available': False, 'scores': {}}
    db = dbs[0]
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = [dict(r) for r in connection.execute('SELECT f.name, u.num_frames, u.alignment_log_likelihood, u.speech_log_likelihood, u.features FROM utterance u JOIN file f ON f.id=u.file_id')]
        speakers = [dict(r) for r in connection.execute('SELECT name, cmvn, fmllr FROM speaker')]
        variants = [dict(r) for r in connection.execute('SELECT p.pronunciation,p.probability,p.silence_after_probability,p.silence_before_correction,p.non_silence_before_correction,p.generated_by_rule FROM pronunciation p JOIN word w ON w.id=p.word_id WHERE w.word=? ORDER BY p.pronunciation', (word,))]
    scores = {}
    for row in rows:
        # Hash the actual complete feature archive, including its frame keys.
        # Ordering differences conservatively make comparability inconclusive/false.
        feature = row.pop('features')
        path = Path(feature.rsplit(':',1)[0]) if feature else None
        row['feature_archive_sha256'] = digest(path) if path and path.is_file() else None
        row['feature_archive_path'] = str(path) if path else None
        scores[row.pop('name')] = row
    return {'database_available':True,'database':pin(db),'scores':scores,'speakers':speakers,
            'target_pronunciations':variants,
            'transform_artifacts':[pin(p) for p in sorted((folder/'mfa-temp').rglob('trans*.ark'))]}


def align_condition(plan_path, plan, group, condition, output):
    spec = plan['targets'][group['target_id']]
    folder = private(output) / 'runs' / group['group_id'] / condition
    receipt_path = folder / 'condition-receipt.json'
    cases = {c['case_id']:c for c in plan['cases']}
    members = [cases[c] for c in group['case_ids']]
    common = {'case_ids':group['case_ids'], 'speaker_id':group['speaker_id'],
        'inputs':{c['case_id']:{'audio':c['audio'], 'transcript':c['transcript']} for c in members},
        'configuration':plan['configuration']}
    signature = hashlib.sha256(evidence_json(common).encode('utf-8')).hexdigest()
    dictionary = spec['dictionaries'].get(condition)
    if receipt_path.exists():
        receipt = load(receipt_path)
        if receipt['common_input_signature'] != signature or receipt['plan'] != pin(plan_path):
            raise ValueError('CONDITION_CONTEXT_CHANGED')
        for ref in receipt['artifacts']: verify(ref)
        return receipt
    if folder.exists(): raise ValueError('INCOMPLETE_CONDITION_PRESERVED_REQUIRES_EXPLICIT_RECOVERY')
    folder.mkdir(parents=True)
    if dictionary is None:
        return load(save(receipt_path, {'plan':pin(plan_path),'condition':condition,'group':group,
            'common_input_signature':signature,'process_returncode':None,'status':'UNSUPPORTED_REDUCED_HYPOTHESIS',
            'artifacts':[],'grids':{},'database_evidence':{'scores':{}},'case_count':len(members)}))
    dictionary_path = verify(dictionary['artifact'])
    (folder/'input').mkdir()
    # Neutral filenames contain no factor, sample boundaries, duration, or variant.
    stems = {c['case_id']:f"item{i:03d}" for i,c in enumerate(members)}
    for case in members:
        for field,suffix in (('audio','.wav'),('transcript','.lab')):
            source = verify(case[field]); target = folder/'input'/(stems[case['case_id']]+suffix)
            shutil.copyfile(source,target)
            if digest(target)!=case[field]['sha256']: raise ValueError('MFA_PREPARED_INPUT_CHANGED')
    env = os.environ.copy()
    env['MFA_ROOT_DIR'] = str(folder/'mfa-root')
    # Explicit paths preserve locked models while keeping per-run global caches isolated.
    argv = [str(R/'.tools/Library/bin/micromamba.exe'),'--no-rc','run','-p',str(R/'.envs/mfa'),
        'mfa','align',str(folder/'input'),str(dictionary_path),str(R/'.mfa/pretrained_models/acoustic/japanese_mfa.zip'),str(folder/'aligned'),
        '--g2p_model_path',str(R/'.mfa/pretrained_models/g2p/japanese_mfa.zip'),
        '--temporary_directory',str(folder/'mfa-temp'),'--single_speaker','--num_jobs','1','--no_use_postgres','--clean']
    with (folder/'alignment.log').open('xb') as stream:
        process = subprocess.run(argv,cwd=R,env=env,stdout=stream,stderr=subprocess.STDOUT)
    db = database_evidence(folder, spec['hypotheses']['target']['surface'])
    grids = {c['case_id']:pin(folder/'aligned'/(stems[c['case_id']]+'.TextGrid')) if (folder/'aligned'/(stems[c['case_id']]+'.TextGrid')).exists() else None for c in members}
    artifacts = [pin(p) for p in sorted(folder.rglob('*')) if p.is_file() and (
        p.parent==folder/'input' or p.suffix.lower()=='.textgrid' or p.name in ('alignment.log','input.yaml')
        or p.name=='input.db' or p.name.startswith('final_features') or p.name.startswith('trans.') or p.name=='cmvn.ark')]
    value = {'plan':pin(plan_path),'condition':condition,'group':group,'common_input_signature':signature,
        'dictionary':dictionary['artifact'],'process_returncode':process.returncode,
        'status':'PROCESS_COMPLETED' if process.returncode==0 else 'ALIGNMENT_FAILED',
        'case_count':len(members),'argv':argv,'environment_policy':'ISOLATED_MFA_ROOT_EXPLICIT_IDENTICAL_LOCKED_MODEL_PATHS',
        'stems':stems,'grids':grids,'database_evidence':db,'artifacts':artifacts}
    save(receipt_path,value)
    print(group['group_id']+' '+condition+' rc='+str(process.returncode)+' grids='+str(sum(g is not None for g in grids.values())),flush=True)
    return load(receipt_path)


def run(plan_path, output, workers=3):
    output = private(output); plan = load(plan_path)
    if plan['code_sha256'] != code_pins(): raise ValueError('PLANNED_EXECUTION_CODE_CHANGED')
    jobs = [(g,c) for g in plan['groups'] for c in plan['conditions']]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(align_condition,plan_path,plan,g,c,output) for g,c in jobs]
        receipts = [f.result() for f in futures]
    return save(output/'execution-index.json',{'plan':pin(plan_path),'condition_runs':len(receipts),
        'expected_condition_cases':plan['expected_condition_cases'],
        'accounted_condition_cases':sum(int(r['case_count']) for r in receipts),
        'receipts':[pin(output/'runs'/r['group']['group_id']/r['condition']/'condition-receipt.json') for r in receipts]})
