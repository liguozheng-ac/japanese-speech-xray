"""Independent private reconstruction of case coverage, PCM truth and summaries."""
from collections import Counter
from pathlib import Path
from fractions import Fraction
import numpy as np
import soundfile as sf
from speech_xray.acoustics.models import evidence_json
from speech_xray.acoustics.timing import quantize_interval
from speech_xray.reference.manifest import load_manifest
from speech_xray.reference.integrity import validate_entry
from speech_xray.reference.json_input import read_json
from speech_xray.reference.models import ReferenceManifest, ReferenceEntry, ArtifactReference
from speech_xray.corpus.batch_plan import digest
from . import FACTORS, MATERIAL_KIND
from .artifacts import load, verify, pin
from .runner import case_id
from .metrics import summarize, recovery
from .perturbation import expected_samples


def audit_benchmark(plan_path, root):
    root = Path(root)
    plan = load(plan_path)
    expected = {case_id(base, factor) for base in plan['bases'] for factor in FACTORS}
    index = load(root / 'case-index.json')
    if len(index) != 180 or len(expected) != 180 or {row['case_id'] for row in index} != expected:
        raise ValueError('PRIVATE_BENCHMARK_COVERAGE_INVALID')
    base_map = {base['base_id']: base for base in plan['bases']}
    if len(base_map) != 15:
        raise ValueError('PRIVATE_BASE_COUNT_INVALID')
    originals, population_hashes = {}, set()
    for base in plan['bases']:
        m = load_manifest(verify(base['reference_manifest']))
        p = read_json(verify(base['reference_profile']))[0]
        if len(m.entries) != 100 or p['speaker_count'] != 100 or p['rejected_take_count'] != 0:
            raise ValueError('REFERENCE_POPULATION_MUST_REMAIN_N100')
        speakers = sorted({entry.speaker_id for entry in m.entries})[:3]
        if base['speaker_id'] not in speakers:
            raise ValueError('OUTCOME_INDEPENDENT_SELECTION_CHANGED')
        entry = next(entry for entry in m.entries if entry.speaker_id == base['speaker_id'])
        valid = validate_entry(m, entry)
        pcm, rate = sf.read(verify(base['sources']['audio']), dtype='int32', always_2d=True)
        first, last = quantize_interval(valid.span.start_ms, valid.span.end_ms, rate)
        if (first, last) != (base['target_sample_start'], base['target_sample_end']):
            raise ValueError('ORIGINAL_TARGET_SAMPLE_DOMAIN_CHANGED')
        originals[base['base_id']] = (pcm, rate)
        population_hashes.update(dict(entry.sources)['audio'].sha256 for entry in m.entries)
    rows = []
    failure_counts = Counter()
    for item in index:
        row = read_json(verify(item['result']))[0];rows.append(row)
        base = base_map[row['base_id']]
        if row['material_kind'] != MATERIAL_KIND or row['factor'] not in FACTORS:
            raise ValueError('CONTROLLED_CASE_PROVENANCE_INVALID')
        gt = row['ground_truth']
        if gt is None:
            if 'MANIPULATION_FAILURE' not in row['pipeline']['failure_categories']:
                raise ValueError('MISSING_MANIPULATION_TRUTH_NOT_DECLARED')
            continue
        original, rate = originals[row['base_id']]
        first, last = int(base['target_sample_start']), int(base['target_sample_end'])
        size = expected_samples(last - first, row['factor'])
        path = root / 'cases' / row['case_id'] / 'perturbed.wav'
        output, output_rate = sf.read(path, dtype='int32', always_2d=True)
        info = sf.info(path)
        if (digest(path) != gt['output_audio_sha256'] or output_rate != rate or info.channels != original.shape[1]
                or info.subtype != gt['pcm_subtype'] or len(output) != len(original) - (last-first) + size
                or gt['actual_perturbed_duration_samples'] != size or gt['expected_perturbed_duration_samples'] != size
                or (gt['original_target_sample_start'], gt['original_target_sample_end']) != (first, last)
                or (gt['perturbed_target_sample_start'], gt['perturbed_target_sample_end']) != (first, first+size)
                or not np.array_equal(original[:first], output[:first])
                or not np.array_equal(original[last:], output[first+size:])):
            raise ValueError('INDEPENDENT_PCM_MANIPULATION_AUDIT_FAILED')
        if row['factor'] != '1.00' and gt['output_audio_sha256'] in population_hashes:
            raise ValueError('PERTURBED_AUDIO_LEAKED_INTO_ORIGINAL_REFERENCE')
        for ref in row['pipeline']['sources'].values(): verify(ref)
        if row['pipeline']['checks']['deviation_evidence_available']:
            refs = row['pipeline']['sources']
            entry = ReferenceEntry(base['prompt_id'], base['target']['target_id'], base['speaker_id'], row['case_id'],
                row['case_id'], row['pipeline']['estimated_span']['id'],
                tuple((key, ArtifactReference(**refs[key])) for key in ('audio','transcript','alignment','mora_analysis','acoustic_evidence')))
            original_manifest = load_manifest(base['reference_manifest']['path'])
            context = ReferenceManifest('stress-audit:' + row['case_id'], base['prompt_id'], refs['transcript']['sha256'],
                original_manifest.target, (('material_kind', MATERIAL_KIND),), 'Ephemeral stress audit', (entry,), '', '')
            validate_entry(context, entry)
            if row['pipeline']['deviation']['reference_n'] != 100:
                raise ValueError('CASE_REFERENCE_N_CHANGED')
        if evidence_json(recovery(gt, row['pipeline'])) != evidence_json(row['recovery']):
            raise ValueError('RECOVERY_ERROR_NOT_REPRODUCIBLE')
        failure_counts.update(row['pipeline']['failure_categories'])
    actual = load(root / 'benchmark-summary.json')
    if evidence_json(summarize(rows, expected)) != evidence_json(actual):
        raise ValueError('SUMMARY_NOT_REPRODUCIBLE_FROM_ALL_CASES')
    controls = load(root / 'controls-audit.json')
    if controls['case_count'] != 15 or controls['all_exact'] is not True:
        raise ValueError('FACTOR_ONE_CONTROLS_NOT_VERIFIED')
    return {'schema_version': '0.1', 'case_count': len(rows), 'factor_counts': dict(Counter(row['factor'] for row in rows)),
        'base_count': len(base_map), 'target_count': len({row['target_id'] for row in rows}),
        'exact_sample_domain_and_unchanged_pcm_verified': True, 'all_case_source_hashes_verified': True,
        'summary_reconstructed_from_all_cases': True, 'successful_case_integrity_replayed': True,
        'control_case_count': 15, 'controls_exact': True, 'reference_n_unchanged': 100,
        'perturbed_reference_observations_added': 0, 'learner_observations_added': 0,
        'REAL_LABELLED_LEARNER_DATA_READY': False, 'failure_categories': dict(failure_counts),
        'plan': pin(plan_path), 'summary': pin(root/'benchmark-summary.json')}
