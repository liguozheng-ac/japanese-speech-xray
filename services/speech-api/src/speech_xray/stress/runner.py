"""Private, resumable real-WAV benchmark via the locked MFA adapter."""
from pathlib import Path
import shutil
from speech_xray.corpus.pipeline import mfa_align
from speech_xray.corpus.batch_plan import pipeline_configuration, digest, object_hash
from speech_xray.reference.json_input import read_json
from speech_xray.acoustics.models import evidence_json
from . import FACTORS, MATERIAL_KIND
from .artifacts import private, save, load, pin, verify
from .perturbation import manipulate
from .pipeline import analyse, reference_for
from .metrics import recovery, f0_region, control_semantics, summarize


def case_id(base, factor):
    return base['base_id'] + '__factor' + factor.replace('.', 'p')


def manipulation_failure(base, factor, error, output):
    """Preserve every requested case even when no manipulated WAV can be made."""
    ident = case_id(base, factor)
    row = {'schema_version': '0.1', 'material_kind': MATERIAL_KIND, 'case_id': ident,
        'base_id': base['base_id'], 'target_id': base['target']['target_id'], 'speaker_id': base['speaker_id'],
        'factor': factor, 'ground_truth': None, 'recovery': None, 'control_verification': None,
        'pitch': {'before': {'median_f0_hz': None}, 'after': {'median_f0_hz': None}, 'median_f0_delta_hz': None},
        'pipeline': {'final_status': 'ABSTAIN', 'checks': {key: False for key in ('mfa_completed', 'textgrid_valid',
            'target_phone_found', 'long_vowel_mapping_valid', 'mora_span_preserved', 'target_inside_wav_domain',
            'acoustic_evidence_available', 'normalized_duration_available', 'deviation_evidence_available')},
            'failure_categories': ['MANIPULATION_FAILURE'], 'reason_codes': [str(error)], 'sources': {},
            'estimated_span': None, 'duration': None, 'deviation': None}}
    save(private(output) / 'cases' / ident / 'case-result.json', row)
    return row


def align_group(inputs, folder):
    """One true speaker, original known transcript, no boundaries or factors."""
    if (not inputs or len({item['stem'] for item in inputs}) != len(inputs)
            or len({item['stem'].split('__')[0] for item in inputs}) != 1):
        raise ValueError('MFA_STRESS_BATCH_REQUIRES_DISTINCT_CASES_FROM_ONE_SPEAKER')
    folder = private(folder)
    receipt = folder / 'mfa-receipt.json'
    signature = object_hash({'inputs': inputs, 'configuration': pipeline_configuration()})
    if receipt.exists():
        previous = load(receipt)
        if previous['input_signature'] != signature:
            raise ValueError('MFA_INPUT_CONTEXT_CHANGED')
        for ref in previous['artifacts']:
            verify(ref)
        return {**previous, 'execution_cache_hit': True}
    if folder.exists():
        raise ValueError('INCOMPLETE_MFA_ATTEMPT_PRESERVED_REQUIRES_NEW_RUN_DIRECTORY')
    (folder / 'input').mkdir(parents=True)
    for item in inputs:
        for key, suffix in (('audio', '.wav'), ('transcript', '.lab')):
            source = verify(item[key]); target = folder / 'input' / (item['stem'] + suffix)
            shutil.copyfile(source, target)
            if digest(target) != item[key]['sha256']:
                raise ValueError('PREPARED_MFA_INPUT_CHANGED')
    failure = None
    try:
        mfa_align({'run_directory': str(folder), 'textgrid': str(folder / 'aligned' / (inputs[0]['stem'] + '.TextGrid'))}, None)
    except (OSError, ValueError, RuntimeError) as error:
        failure = {'type': type(error).__name__, 'reason': str(error)}
    grids = {item['stem']: str(folder / 'aligned' / (item['stem'] + '.TextGrid')) for item in inputs}
    value = {'input_signature': signature, 'mfa_process_completed': failure is None, 'failure': failure,
        'utterance_count': len(inputs), 'grids': grids,
        'artifacts': [pin(path) for path in sorted(folder.rglob('*')) if path.is_file()
            and (path.parent == folder / 'input' or path.suffix.lower() == '.textgrid' or path.name == 'alignment.log')]}
    save(receipt, value)
    return {**load(receipt), 'execution_cache_hit': False}


def prepare_case(base, factor, root):
    folder = private(private(root) / 'cases' / case_id(base, factor))
    receipt = folder / 'manipulation-ground-truth.json'
    if receipt.exists():
        gt = load(receipt)
        if gt['input_audio_sha256'] != base['sources']['audio']['sha256'] or gt['requested_factor_decimal'] != factor:
            raise ValueError('MANIPULATION_INPUT_CONTEXT_CHANGED')
        if digest(folder / 'perturbed.wav') != gt['output_audio_sha256']:
            raise ValueError('PERTURBED_AUDIO_CHANGED')
        return folder, gt
    source = verify(base['sources']['audio'])
    gt = manipulate(source, folder / 'perturbed.wav', int(base['target_sample_start']),
        int(base['target_sample_end']), factor)
    save(receipt, gt)
    return folder, load(receipt)


def post_case(base, factor, folder, gt, aligned, stem, reference):
    path = folder / 'case-result.json'
    if path.exists():
        previous = load(path)
        for ref in previous['pipeline']['sources'].values(): verify(ref)
        if previous['ground_truth'] != gt:
            raise ValueError('GROUND_TRUTH_CHANGED_AFTER_ANALYSIS')
        return previous
    prepared_lab = Path(aligned['grids'][stem]).parent.parent / 'input' / (stem + '.lab')
    analyse(case_id(base, factor), folder / 'perturbed.wav', aligned['grids'][stem], prepared_lab,
        base, folder / 'analysis', reference, mfa_completed=aligned['mfa_process_completed'])
    result = load(folder / 'analysis/pipeline-result.json')
    original_acoustic = read_json(verify(base['sources']['acoustic_evidence']))[0]
    current_acoustic = read_json(verify(result['sources']['acoustic_evidence']))[0] if 'acoustic_evidence' in result['sources'] else {}
    before = f0_region(original_acoustic, int(gt['original_target_sample_start']), int(gt['original_target_sample_end']))
    after = f0_region(current_acoustic, int(gt['perturbed_target_sample_start']), int(gt['perturbed_target_sample_end']))
    pitch = {'before': before, 'after': after, 'median_f0_delta_hz':
        after['median_f0_hz'] - before['median_f0_hz'] if before['median_f0_hz'] is not None and after['median_f0_hz'] is not None else None,
        'meaning': 'WITHIN_SAME_NATIVE_BASE_MANIPULATION_ARTIFACT_CHECK_NOT_PITCH_NORM'}
    row = {'schema_version': '0.1', 'material_kind': MATERIAL_KIND,
        'case_id': case_id(base, factor), 'base_id': base['base_id'], 'target_id': base['target']['target_id'],
        'speaker_id': base['speaker_id'], 'factor': factor, 'ground_truth': gt,
        'pipeline': result, 'recovery': recovery(gt, result), 'pitch': pitch,
        'control_verification': control_semantics(base, result, original_acoustic, current_acoustic) if factor == '1.00' else None}
    save(path, row)
    return load(path)


def run(plan_path, output, execute=False, controls_only=False):
    plan = load(plan_path); output = private(output)
    if evidence_json(plan['configuration']) != evidence_json(pipeline_configuration(run_label='controlled-perturbation')):
        raise ValueError('FROZEN_PIPELINE_CONFIGURATION_CHANGED')
    expected = [case_id(base, factor) for base in plan['bases'] for factor in FACTORS]
    if not execute:
        return {'status': 'PLANNED', 'case_count': len(expected), 'case_ids': expected, 'dry_run': True}
    verify(plan['accepted_build'])
    if (len(expected) != 180 or len(set(expected)) != 180 or len(plan['bases']) != 15
            or plan['factors'] != list(FACTORS) or plan['material_kind'] != MATERIAL_KIND
            or plan['real_learner_data_allowed'] is not False or plan['perturbed_reference_export_allowed'] is not False):
        raise ValueError('EXACT_FROZEN_CONTROLLED_EXPERIMENT_REQUIRED')
    save(output / 'run-configuration.json', {'plan': pin(plan_path), 'configuration': plan['configuration'],
        'stress_code_identity': {path.name: digest(path) for path in sorted(Path(__file__).parent.glob('*.py'))}})
    references = {base['target']['target_id']: reference_for(base)
        for base in plan['bases'] if base['speaker_id'] == min(b['speaker_id'] for b in plan['bases'])}
    rows = []
    # Exact original MFA corpus contexts first, including support utterances.
    # These support inputs are not additional benchmark cases/reference observations.
    groups = {}
    for base in plan['bases']:
        groups.setdefault(base['control_input_directory'], []).append(base)
    for number, (directory, bases) in enumerate(sorted(groups.items())):
        inputs = [{'stem': lab.stem, 'audio': pin(lab.with_suffix('.wav')), 'transcript': pin(lab)}
                  for lab in sorted(Path(directory).glob('*.lab'))]
        speakers = {item['stem'].split('__')[0] for item in inputs}
        if speakers != {base['speaker_id'] for base in bases}:
            raise ValueError('CONTROL_BATCH_MUST_PRESERVE_ONE_ACTUAL_SPEAKER')
        print('CONTROL_MFA', number + 1, 'inputs', len(inputs), flush=True)
        aligned = align_group(inputs, output / 'mfa-controls' / f'batch-{number:03}')
        print('CONTROL_MFA_RECEIPT', number + 1, 'verified_cache_hit', aligned['execution_cache_hit'], flush=True)
        for base in bases:
            folder, gt = prepare_case(base, '1.00', output)
            row = post_case(base, '1.00', folder, gt, aligned, Path(base['sources']['transcript']['path']).stem,
                           references[base['target']['target_id']])
            rows.append(row)
    controls = {'case_count': len(rows), 'all_exact': all(all(row['control_verification'].values()) for row in rows),
        'cases': [{'case_id': row['case_id'], 'verification': row['control_verification']} for row in rows]}
    save(output / 'controls-audit.json', controls)
    if not controls['all_exact']:
        return {'status': 'CONTROL_DIVERGENCE_REQUIRES_INVESTIGATION', 'controls': controls}
    if controls_only:
        return {'status': 'CONTROLS_VERIFIED', 'controls': controls}
    for speaker in sorted({base['speaker_id'] for base in plan['bases']}):
        bases = [base for base in plan['bases'] if base['speaker_id'] == speaker]
        inputs, jobs = [], []
        for base in bases:
            for factor in FACTORS:
                if factor == '1.00': continue
                try:
                    folder, gt = prepare_case(base, factor, output)
                except (OSError, ValueError, RuntimeError) as error:
                    rows.append(manipulation_failure(base, factor, error, output))
                    continue
                stem = case_id(base, factor)
                inputs.append({'stem': stem, 'audio': pin(folder / 'perturbed.wav'), 'transcript': base['sources']['transcript']})
                jobs.append((base, factor, folder, gt, stem))
        print('PERTURBED_MFA', speaker, 'cases', len(inputs), flush=True)
        if not inputs: continue
        aligned = align_group(inputs, output / 'mfa-perturbed' / speaker)
        print('PERTURBED_MFA_RECEIPT', speaker, 'verified_cache_hit', aligned['execution_cache_hit'], flush=True)
        for base, factor, folder, gt, stem in jobs:
            row = post_case(base, factor, folder, gt, aligned, stem, references[base['target']['target_id']])
            rows.append(row)
            print('CASE', len(rows), '/', len(expected), row['factor'], row['pipeline']['final_status'], flush=True)
    rows.sort(key=lambda row: (row['base_id'], FACTORS.index(row['factor'])))
    save(output / 'case-index.json', [{'case_id': row['case_id'], 'result': pin(output / 'cases' / row['case_id'] / 'case-result.json')} for row in rows])
    summary = summarize(rows, expected)
    save(output / 'benchmark-summary.json', summary)
    return summary
