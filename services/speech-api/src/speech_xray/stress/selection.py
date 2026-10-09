"""Pre-outcome selection from stable accepted reference identities only."""
from pathlib import Path
import re
import soundfile as sf
from speech_xray.reference.json_input import read_json
from speech_xray.reference.manifest import load_manifest, PROJECT_ROOT
from speech_xray.reference.integrity import validate_entry
from speech_xray.acoustics.timing import quantize_interval
from speech_xray.corpus.batch_plan import pipeline_configuration, digest
from . import FACTORS, MATERIAL_KIND
from .artifacts import save, pin, verify

TARGET_SUFFIXES = ('010-w000-m001', '051-w000-m001', '053-w001-m002', '063-w000-m000', '074-w001-m001')


def select_bases(build_manifest, output):
    build_manifest = Path(build_manifest).resolve()
    if not build_manifest.is_relative_to((PROJECT_ROOT / 'data/private').resolve()):
        raise ValueError('ACCEPTED_BUILD_MUST_BE_PRIVATE')
    build, _ = read_json(build_manifest)
    if build['build_id'] != 'task009-v2':
        raise ValueError('ACCEPTED_TASK009_V2_REQUIRED')
    rows = sorted(build['full'], key=lambda row: row['target_id'])
    if tuple(row['target_id'].split('voiceactress100_')[-1] for row in rows) != TARGET_SUFFIXES:
        raise ValueError('EXACT_FIVE_ACCEPTED_TARGETS_REQUIRED')
    bases = []
    for row in rows:
        manifest_path = verify(row['manifest_artifact'])
        profile_path = verify(row['profile_artifact'])
        manifest = load_manifest(manifest_path)
        profile, _ = read_json(profile_path)
        if (profile['speaker_count'] != 100 or profile['take_count'] != 100
                or profile['rejected_take_count'] != 0 or len(manifest.entries) != 100):
            raise ValueError('COMPLETE_N100_REFERENCE_REQUIRED')
        # Deliberately independent of duration, F0, or perturbation results.
        speakers = sorted({entry.speaker_id for entry in manifest.entries})[:3]
        for speaker in speakers:
            entries = sorted((entry for entry in manifest.entries if entry.speaker_id == speaker), key=lambda entry: entry.take_id)
            if len(entries) != 1:
                raise ValueError('ONE_STABLE_TAKE_PER_SPEAKER_REQUIRED')
            entry = entries[0]
            validated = validate_entry(manifest, entry)
            refs = entry.to_dict()['sources']
            info = sf.info(refs['audio']['path'])
            first, last = quantize_interval(validated.span.start_ms, validated.span.end_ms, info.samplerate)
            if not 0 <= first < last <= info.frames:
                raise ValueError('ACCEPTED_TARGET_DOMAIN_INVALID')
            mora, _ = read_json(Path(refs['mora_analysis']['path']))
            word = mora['words'][manifest.target.word_index]
            transcript = Path(refs['transcript']['path'])
            grid = transcript.parent.parent / 'aligned' / (transcript.stem + '.TextGrid')
            if not grid.is_file():
                raise ValueError('ACCEPTED_CONTROL_TEXTGRID_UNAVAILABLE')
            bases.append({'base_id': speaker + '__' + manifest.target.target_id,
                'speaker_id': speaker, 'prompt_id': manifest.prompt_id, 'target': manifest.target.to_dict(),
                'surface': word['surface'], 'reading': word['reading'], 'sources': refs,
                'accepted_textgrid': pin(grid), 'accepted_original_span': validated.span.to_dict(),
                'target_sample_start': first, 'target_sample_end': last,
                'reference_manifest': row['manifest_artifact'], 'reference_profile': row['profile_artifact'],
                'control_input_directory': str(transcript.parent), 'reference_speaker_overlap': True})
    plan = {'schema_version': '0.1', 'representation': 'CONTROLLED_PERTURBATION_EXPERIMENT_PLAN',
        'material_kind': MATERIAL_KIND, 'accepted_build': pin(build_manifest),
        'selection_rule': 'LEXICOGRAPHIC_FIRST_THREE_DISTINCT_SPEAKER_IDS_ONE_ACCEPTED_TAKE_EACH_PER_TARGET',
        'selection_uses_outcomes_or_duration_statistics': False,
        'factors': list(FACTORS), 'base_count': 15, 'expected_case_count': 180, 'bases': bases,
        'configuration': pipeline_configuration(run_label='controlled-perturbation'),
        'reference_population_policy': 'UNCHANGED_ACCEPTED_N100_IN_POPULATION_ENGINEERING_COMPARISON',
        'perturbed_reference_export_allowed': False, 'real_learner_data_allowed': False}
    save(output, plan)
    return plan
