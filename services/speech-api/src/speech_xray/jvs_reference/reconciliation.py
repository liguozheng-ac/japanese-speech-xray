"""Replay accepted evidence into a separate private reference identity, without MFA."""

from pathlib import Path
from fractions import Fraction
import hashlib

from speech_xray.corpus.batch_plan import digest, pipeline_configuration
from speech_xray.reference.json_input import read_json
from speech_xray.reference.numeric import decimal_ratio
from .cache import read_control, safe_directory, validate_artifacts
from .build import build_targets, save_verified

BASELINE = 'cb6975d270f87ce48d7905de8c0328bb45c43d14'
INTEGRITY_PATH = 'services/speech-api/src/speech_xray/reference/integrity.py'
DOMAIN_PATH = 'services/speech-api/src/speech_xray/reference/domains.py'


def ensure_separate_roots(previous, output):
    previous, output = safe_directory(previous), safe_directory(output)
    if previous == output or previous.is_relative_to(output) or output.is_relative_to(previous):
        raise ValueError('RECONCILIATION_REQUIRES_SEPARATE_ROOTS')
    return previous, output


def frozen_files(previous):
    """Stream all files, including retained MFA scratch, without loading models in RAM."""
    records = []
    for path in sorted(p for p in previous.rglob('*') if p.is_file()):
        hasher = hashlib.sha256()
        with path.open('rb') as stream:
            while block := stream.read(1024 * 1024):
                hasher.update(block)
        records.append({'path': path.relative_to(previous).as_posix(),
                        'bytes': path.stat().st_size, 'sha256': hasher.hexdigest()})
    return records


def freeze_previous_build(previous, output):
    previous, output = ensure_separate_roots(previous, output)
    records = frozen_files(previous)
    destination = output/'v1-file-snapshot.json'
    if destination.exists():
        before, _ = read_control(destination)
        if records != before:
            raise ValueError('PREVIOUS_BUILD_CHANGED')
    else:
        save_verified(destination, records)
    return records


def verify_configuration(previous, current):
    """Only downstream reference containment may change; upstream reuse stays pinned."""
    for key in previous.keys() - {'analysis_code_sha256'}:
        if previous[key] != current[key]:
            raise ValueError('REPLAY_CONFIGURATION_CHANGED:' + key)
    old, new = previous['analysis_code_sha256'], current['analysis_code_sha256']
    if set(new) - set(old) != {DOMAIN_PATH} or set(old) - set(new):
        raise ValueError('UNEXPECTED_ANALYSIS_CODE_SET')
    changed = {name for name in old if old[name] != new[name]}
    if changed != {INTEGRITY_PATH}:
        raise ValueError('UNEXPECTED_ANALYSIS_CODE_CHANGE')
    return {'changed': {name: {'v1': old[name], 'v2': new[name]} for name in sorted(changed)},
            'added': {DOMAIN_PATH: new[DOMAIN_PATH]}, 'upstream_identity_unchanged': True}


def compare_profiles(old, new):
    """Compare persisted Decimal features, with signed absolute and relative changes."""
    result = {'v1_N': old['speaker_count'], 'v2_N': new['speaker_count'], 'features': {}}
    for feature, previous in old['feature_statistics'].items():
        current = new['feature_statistics'][feature]
        changes = {}
        for name in ('median', 'mad', 'q25', 'q75', 'iqr', 'minimum', 'maximum'):
            before, after = Fraction(previous[name]), Fraction(current[name])
            delta = after - before
            changes[name] = {'v1': previous[name], 'v2': current[name],
                             'absolute_change': decimal_ratio(delta),
                             'relative_change': decimal_ratio(delta / before) if before else None,
                             'absolute_change_exact': str(delta),
                             'relative_change_exact': str(delta / before) if before else None}
        result['features'][feature] = changes
    return result


def reconcile(source, previous, output):
    previous, output = ensure_separate_roots(previous, output)
    source = safe_directory(source)
    frozen, _ = read_control(output / 'v1-file-snapshot.json')
    pinned = {r['path']: r['sha256'] for r in frozen}
    manifest_path = previous / 'build-manifest-v2.json'
    if digest(manifest_path) != pinned['build-manifest-v2.json']:
        raise ValueError('FROZEN_BUILD_MANIFEST_CHANGED')
    old, old_hash = read_control(manifest_path)
    configuration = pipeline_configuration()
    reuse = verify_configuration(old['configuration'], configuration)
    audit_path, smoke_path = source/'reports/full-audit-v1.json', source/'reports/full-smoke-v2.json'
    audit, audit_hash = read_control(audit_path)
    smoke, smoke_hash = read_control(smoke_path)
    if (audit_hash != old['lineage']['source_artifacts']['audit']
            or smoke_hash != old['lineage']['source_artifacts']['smoke']):
        raise ValueError('ACCEPTED_SOURCE_IDENTITY_CHANGED')
    data = {'inventory': audit['inventory'], 'discovery': audit['discovery'],
            'targets': smoke['reviewed_recommendation']['selected_targets']}
    if sorted(t['target_id'] for t in data['targets']) != old['lineage']['final_target_ids']:
        raise ValueError('ACCEPTED_TARGET_SET_CHANGED')
    official = {p['corpus_prompt_id']: p for p in audit['inventory']['prompts']}
    jobs = {(j['speaker_id'], j['prompt_id']): {**j, 'text': official[j['prompt_id']]['text'],
            'source_type': 'EXTERNAL_RESEARCH_CORPUS'} for j in audit['inventory']['records']}
    bundles = {}
    for path in sorted((previous/'utterance-cache').glob('*/attempt-*/receipt.json')):
        if digest(path) != pinned[path.relative_to(previous).as_posix()]:
            raise ValueError('FROZEN_RECEIPT_CHANGED')
        bundle, _ = read_control(path)
        validate_artifacts(bundle, bundle['signature'])
        audio = Path(bundle['artifacts']['audio']['path'])
        key = (audio.parents[2].name, audio.stem)
        if key in bundles or key not in jobs:
            raise ValueError('DUPLICATE_OR_UNKNOWN_UTTERANCE')
        bundles[key] = bundle
    if len(bundles) != old['utterance_count']:
        raise ValueError('ATTEMPTED_UTTERANCE_SET_CHANGED')
    # Check attempted membership against v1 ledgers rather than infer success.
    for row in old['qualification'] + old['full']:
        ref = row['observations_artifact']
        if digest(ref['path']) != ref['sha256']:
            raise ValueError('V1_LEDGER_CHANGED')
        ledger, _ = read_control(ref['path'])
        if any((r['speaker_id'], r['prompt_id']) not in bundles for r in ledger):
            raise ValueError('ATTEMPTED_UTTERANCE_MISSING')
    qualification_jobs = [jobs[k] for k in sorted(bundles) if k[0] in {f'jvs{i:03}' for i in range(1, 6)}]
    qualification, _ = build_targets(data, qualification_jobs, bundles, output, 'qualification', build_id='task009-v2')
    print('qualification replay complete', flush=True)
    selected_ids = {r['target_id'] for r in old['full']}
    full_data = {**data, 'targets': [t for t in data['targets'] if t['target_id'] in selected_ids]}
    full_prompts = {r['prompt_id'] for r in old['full']}
    full_jobs = [jobs[k] for k in sorted(bundles) if k[1] in full_prompts]
    full, _ = build_targets(full_data, full_jobs, bundles, output, 'full',
                            {r['target_id']: r for r in qualification}, build_id='task009-v2')
    comparisons = {}
    for row in full:
        v1 = next(r for r in old['full'] if r['target_id'] == row['target_id'])
        if digest(v1['profile_artifact']['path']) != v1['profile_artifact']['sha256']:
            raise ValueError('V1_PROFILE_CHANGED')
        before, _ = read_json(Path(v1['profile_artifact']['path']))
        after, _ = read_json(Path(row['profile_artifact']['path']))
        comparisons[row['target_id']] = compare_profiles(before, after)
    deferred = [{'target_id': r['target_id'], 'v1_N': r['valid_reference_observation_speakers'],
                 'v2_N': next(v['valid_reference_observation_speakers'] for v in qualification if v['target_id']==r['target_id']),
                 'v1_status': r['qualification_status'],
                 'v2_status': next(v['qualification_status'] for v in qualification if v['target_id']==r['target_id'])}
                for r in old['qualification'] if r['qualification_status'] != 'QUALIFIED_FOR_FULL_BUILD']
    save_verified(output/'profile-comparison.json', comparisons)
    save_verified(output/'deferred-reassessment.json', deferred)
    result = {'build_id':'task009-v2', 'baseline_commit':BASELINE, 'source_type':'EXTERNAL_RESEARCH_CORPUS',
              'previous_manifest_sha256':old_hash, 'v1_snapshot_sha256':digest(output/'v1-file-snapshot.json'),
              'configuration':configuration, 'reuse_verification':reuse, 'qualification':qualification, 'full':full,
              'utterance_count':len(bundles), 'additional_full_profiles':0, 'new_mfa_runs':0, 'new_acoustic_runs':0,
              'no_outlier_removal':True, 'minimum_independent_speakers':5}
    save_verified(output/'build-manifest.json', result)
    print('full reference replay complete', flush=True)
    return result
