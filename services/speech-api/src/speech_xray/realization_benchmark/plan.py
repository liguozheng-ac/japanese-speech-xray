"""Freeze existing WAVs and an isolated three-condition design before outcomes."""
from dataclasses import asdict
from pathlib import Path
import json
import subprocess
import zipfile
from speech_xray.corpus.batch_plan import digest, model_resources
from speech_xray.corpus.validation import PROJECT_ROOT as R
from speech_xray.realization import Target, derive_hypotheses, override_lexicon, CONDITIONS
from speech_xray.alignment.textgrid_parser import parse_textgrid
from .artifacts import private, save, load, pin, verify

FACTORS = ('0.20', '0.30', '0.40', '0.50', '0.60', '0.70', '0.80', '0.90', '1.00', '1.10', '1.25', '1.50')
TARGET_SUFFIXES = ('010-w000-m001', '051-w000-m001', '053-w001-m002', '063-w000-m000', '074-w001-m001')


def code_pins():
    return {p.relative_to(R).as_posix(): digest(p) for folder in ('realization', 'realization_benchmark')
            for p in sorted((R / 'services/speech-api/src/speech_xray' / folder).glob('*.py'))}


def prepare(source_plan, case_index, capability_audit, output):
    output = private(output)
    destination = output / 'experiment-plan.json'
    if destination.exists(): raise ValueError('EXPERIMENT_PLAN_ALREADY_FIXED')
    source = load(source_plan); index = load(case_index)
    assert len(source['bases']) == 15 and len(index) == 180
    resources = model_resources()
    if any(r['actual_sha256'] != r['expected_sha256'] for r in resources):
        raise ValueError('LOCKED_MODEL_CHANGED')
    model = R / '.mfa/pretrained_models/acoustic/japanese_mfa.zip'
    official = R / '.mfa/pretrained_models/dictionary/japanese_mfa.dict'
    with zipfile.ZipFile(model) as archive:
        meta = json.loads(archive.read('japanese_mfa/meta.json'))
        phone_table = archive.read('japanese_mfa/phones.txt').decode()
    save(output / 'locked-phone-inventory.json', {'meta_phones': meta['phones'], 'phone_table': phone_table,
        'phone_groups': meta['phone_groups'], 'model_sha256': digest(model)})
    inventory = set(meta['phones']); pairs = []
    for long in inventory:
        if long.endswith('ː') and long[:-1] in inventory and any(long in group and long[:-1] in group for group in meta['phone_groups'].values()):
            pairs.append((long, long[:-1]))
    audit = load(capability_audit); original = official.read_bytes()
    targets = {}; bases = []
    for base in source['bases']:
        ident = base['target']['target_id']
        if not any(ident.endswith(s) for s in TARGET_SUFFIXES): raise ValueError('UNPLANNED_TARGET')
        alignment = parse_textgrid(verify(base['accepted_textgrid']))
        word = [w for w in alignment.words if w.label][int(base['target']['word_index'])]
        phones = [p for p in alignment.phones if p.label and p.start_ms >= word.start_ms and p.end_ms <= word.end_ms]
        span = base['accepted_original_span']
        positions = [i for i,p in enumerate(phones) if p.label == base['target']['phone_label'] and p.start_ms == span['start_ms'] and p.end_ms == span['end_ms']]
        if len(positions) != 1 or word.label != base['surface']: raise ValueError('ACCEPTED_CANONICAL_PHONE_AMBIGUOUS')
        target = Target(ident, base['surface'], base['reading'], int(base['target']['word_index']),
                        tuple(int(i) for i in base['target']['word_mora_indices']), base['target']['vowel_class'], base['target']['mapping_basis'])
        h = derive_hypotheses(target, [p.label for p in phones], positions[0], inventory, pairs)
        entries = [e for e in audit['dictionary_entries'] if e['word'] == word.label]
        accepted = [e for e in entries if tuple(e['phones']) == h.canonical]
        if len(accepted) != 1: raise ValueError('CANONICAL_OFFICIAL_ENTRY_AMBIGUOUS')
        specification = {'hypotheses': h.to_dict(), 'official_entries': entries, 'dictionaries': {}}
        if h.reduced is not None:
            for condition in CONDITIONS:
                raw, construction = override_lexicon(original, h, condition, tuple(str(x) for x in accepted[0]['silence_fields']))
                path = output / 'dictionaries' / (ident + '__' + condition + '.dict')
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.exists() and path.read_bytes() != raw: raise ValueError('DICTIONARY_CHANGED')
                if not path.exists(): path.write_bytes(raw)
                specification['dictionaries'][condition] = {'artifact': pin(path), 'construction': construction}
        if ident in targets and targets[ident] != specification: raise ValueError('BASE_CANONICAL_SEQUENCE_DISAGREES')
        targets[ident] = specification
        bases.append({'base_id': base['base_id'], 'speaker_id': base['speaker_id'], 'prompt_id': base['prompt_id'],
                      'target_id': ident, 'original_alignment': base['accepted_textgrid']})
    base_map = {b['base_id']: b for b in bases}; cases = []
    for ref in index:
        result_path = verify(ref['result']); result = load(result_path)
        base = base_map[result['base_id']]
        cases.append({'case_id': result['case_id'], **base, 'factor': result['factor'],
            'audio': pin(result_path.parent / 'perturbed.wav'),
            'transcript': result['pipeline']['sources']['transcript'], 'task012_result': pin(result_path)})
    cases.sort(key=lambda c:(c['target_id'], c['speaker_id'], FACTORS.index(c['factor'])))
    groups=[]
    for target in sorted(targets):
        for speaker in sorted({c['speaker_id'] for c in cases}):
            members=[c['case_id'] for c in cases if c['target_id']==target and c['speaker_id']==speaker]
            if len(members)!=12: raise ValueError('INCOMPLETE_FACTOR_GROUP')
            groups.append({'group_id': speaker+'__'+target, 'target_id': target, 'speaker_id': speaker, 'case_ids':members})
    config={'single_speaker':True,'num_jobs':1,'use_postgres':False,'clean':True,'phone_confidence':False,
        'g2p_model_sha256':digest(R/'.mfa/pretrained_models/g2p/japanese_mfa.zip'),
        'beam':10,'retry_beam':40,'acoustic_scale':0.1,'transition_scale':1.0,'self_loop_scale':0.1,
        'max_active':2500,'lattice_beam':6,'frame_shift_ms':meta['features']['frame_shift'],
        'adaptation':'SINGLE_SPEAKER_DISABLES_FMLLR','mfa_version':audit['mfa_version'],
        'model_sha256':digest(model),'official_dictionary_sha256':digest(official),
        'mfa_source_sha256':audit['source_sha256'],
        'environment_locks':{n:digest(R/'docs'/n) for n in ('task002-conda-win-64.explicit.txt','task004-speech-api-win-64.explicit.txt')},
        'feature_configuration':meta['features'], 'batch_policy':'ONE_TRUE_SPEAKER_ONE_TARGET_ALL_TWELVE_FACTORS',
        'prior_policy':'EXPLICIT_EQUAL_1_0_ZERO_COST_SHARED_SILENCE_FIELDS',
        'outcome_policy':'NO_PRIOR_BEAM_COST_ACOUSTIC_SCALE_TUNING'}
    plan={'schema_version':'0.1','material_kind':'CONTROLLED_REALIZATION_HYPOTHESIS_EXPERIMENT',
        'starting_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=R).decode().strip(),
        'source_plan':pin(source_plan),'source_case_index':pin(case_index),'capability_audit':pin(capability_audit),
        'inventory':pin(output/'locked-phone-inventory.json'),'configuration':config,
        'code_sha256':code_pins(),'targets':targets,'bases':bases,'factors':list(FACTORS),'cases':cases,'groups':groups,
        'conditions':list(CONDITIONS),'expected_condition_cases':540,
        'ground_truth_policy':'POST_ALIGNMENT_ANALYSIS_ONLY_NO_BOUNDARIES_FACTORS_OR_SAMPLES_IN_MFA_INPUT',
        'unsupported_case_policy':'RETAIN_EVERY_REQUESTED_CASE_AND_CONDITION',
        'score_policy':'GATE_ACTUAL_FEATURE_FRAME_AND_ADAPTATION_IDENTITY_DESCRIPTIVE_ONLY_NO_VARIANT_DECISION'}
    save(destination,plan)
    return destination
