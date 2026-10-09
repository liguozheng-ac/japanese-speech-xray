"""Unchanged downstream analysis, without manipulation ground-truth inputs."""
from dataclasses import asdict
from pathlib import Path
from speech_xray.alignment.textgrid_parser import parse_textgrid
from speech_xray.japanese.long_vowel_mapper import analyze_mora
from speech_xray.japanese.reading import SudachiReadingProvider
from speech_xray.acoustics.mora_input import load_mora_analysis
from speech_xray.acoustics.pipeline import extract_acoustic_evidence
from speech_xray.acoustics.audio import load_audio
from speech_xray.acoustics.config import AcousticConfig
from speech_xray.reference.integrity import validate_entry
from speech_xray.reference.domains import interval_inside_audio
from speech_xray.reference.speech_rate import measure_utterance_rate
from speech_xray.reference.normalization import normalize_duration
from speech_xray.reference.models import ReferenceManifest, ReferenceEntry, ArtifactReference, TargetIdentity
from speech_xray.deviation.inputs import verified_reference
from speech_xray.deviation.validation import reference_validation
from speech_xray.deviation.duration import describe_duration, FEATURES, FORMULAS
from . import MATERIAL_KIND
from .artifacts import save, pin, private, verify


def reference_for(base):
    reference = verified_reference(verify(base['reference_manifest']), ArtifactReference(**base['reference_profile']), 'task009-v2')
    reference_validation(reference)
    if len(reference.profile.speakers) != 100:
        raise ValueError('ACCEPTED_REFERENCE_POPULATION_CHANGED')
    return reference


def analyse(case_id, audio_path, textgrid_path, transcript_path, base, output, reference, mfa_completed=False):
    """The signature intentionally accepts no sample start/end or factor."""
    folder = private(output)
    status = {key: False for key in ('mfa_completed', 'textgrid_valid', 'target_phone_found',
        'long_vowel_mapping_valid', 'mora_span_preserved', 'target_inside_wav_domain',
        'acoustic_evidence_available', 'normalized_duration_available', 'deviation_evidence_available')}
    status['mfa_completed'] = mfa_completed
    result = {'schema_version': '0.1', 'representation': 'MFA_ESTIMATED_ALIGNMENT_PIPELINE_RESULT',
        'material_kind': MATERIAL_KIND, 'case_id': case_id, 'base_id': base['base_id'],
        'speaker_id': base['speaker_id'], 'target_id': base['target']['target_id'],
        'checks': status, 'failure_categories': [], 'reason_codes': [], 'sources': {},
        'estimated_span': None, 'rate_context': None, 'duration': None, 'deviation': None}
    stage = 'MFA_FAILURE'
    try:
        result['sources'] = {'audio': pin(audio_path), 'transcript': pin(transcript_path)}
        if result['sources']['transcript']['sha256'] != base['sources']['transcript']['sha256']:
            raise ValueError('TRANSCRIPT_CHANGED_FROM_ACCEPTED_PROMPT')
        alignment = parse_textgrid(Path(textgrid_path))
        status['textgrid_valid'] = True
        result['sources']['textgrid'] = pin(textgrid_path)
        alignment_ref = save(folder / 'alignment.json', alignment.to_dict())
        result['sources']['alignment'] = alignment_ref
        stage = 'MORA_MAPPING_FAILURE'
        mora = analyze_mora(alignment, SudachiReadingProvider())
        mora_ref = save(folder / 'mora-analysis.json', mora.to_dict())
        result['sources']['mora_analysis'] = mora_ref
        result['unresolved_items'] = [item.to_dict() for item in mora.unresolved_items]
        target = base['target']
        words = [word for word in mora.words if word.surface == base['surface']
                 and word.reading_result.reading == base['reading']]
        if len(words) == 1:
            status['target_phone_found'] = any(alignment.phones[i].label == target['phone_label']
                for i in words[0].phone_indices)
        spans = [span for span in mora.long_vowel_spans if span.word_index == target['word_index']
            and mora.words[span.word_index].surface == base['surface']
            and mora.words[span.word_index].reading_result.reading == base['reading']
            and [mora.morae[i].word_mora_index for i in span.mora_indices] == target['word_mora_indices']
            and (span.phone_label, span.vowel_class, span.mapping_basis) ==
                (target['phone_label'], target['vowel_class'], target['mapping_basis'])]
        stage = 'DOMAIN_FAILURE'
        decoded = load_audio(audio_path).metadata
        if not all(interval_inside_audio(word.start_ms, word.end_ms, decoded.frame_count, decoded.sample_rate_hz)
                   for word in alignment.words if word.label.strip()):
            raise ValueError('CORE_WORD_OUTSIDE_AUDIO_DOMAIN')
        # Retain whole-utterance acoustic tracks even when the target did not map.
        stage = 'ACOUSTIC_EXTRACTION_FAILURE'
        acoustic = extract_acoustic_evidence(audio_path, load_mora_analysis(mora_ref['path']))
        if acoustic.config.to_dict() != AcousticConfig().to_dict():
            raise ValueError('ACCEPTED_ACOUSTIC_CONFIGURATION_CHANGED')
        acoustic_ref = save(folder / 'acoustic-evidence.json', acoustic.to_dict())
        result['sources']['acoustic_evidence'] = acoustic_ref
        result['whole_audio_extraction_status'] = acoustic.extraction_status
        if len(spans) != 1:
            stage = 'MORA_MAPPING_FAILURE' if status['target_phone_found'] else 'TARGET_PHONE_NOT_FOUND'
            raise ValueError('ACCEPTED_LEXICAL_TWO_MORA_TARGET_NOT_UNIQUELY_MAPPED')
        span = spans[0]
        status['long_vowel_mapping_valid'] = True
        status['mora_span_preserved'] = span.mora_span == 2
        result['estimated_span'] = span.to_dict()
        stage = 'DOMAIN_FAILURE'
        status['target_inside_wav_domain'] = interval_inside_audio(span.start_ms, span.end_ms,
            decoded.frame_count, decoded.sample_rate_hz)
        if not status['target_inside_wav_domain']:
            raise ValueError('TARGET_OUTSIDE_AUDIO_DOMAIN')
        refs = tuple((key, ArtifactReference(**result['sources'][key])) for key in
                     ('audio', 'transcript', 'alignment', 'mora_analysis', 'acoustic_evidence'))
        identity = TargetIdentity(target['target_id'], target['word_index'], tuple(target['word_mora_indices']),
            target['phone_label'], target['vowel_class'], target['mora_span'], target['mapping_basis'])
        entry = ReferenceEntry(base['prompt_id'], identity.target_id, base['speaker_id'], case_id,
            case_id, span.id, refs)
        # Typed, ephemeral integrity context. This material kind is rejected by
        # the unchanged native manifest loader and never exported as a population.
        context = ReferenceManifest('stress-integrity:' + case_id, base['prompt_id'],
            result['sources']['transcript']['sha256'], identity, (('material_kind', MATERIAL_KIND),),
            'Ephemeral engineering validation context', (entry,), '', '')
        validated = validate_entry(context, entry)
        if (acoustic.audio.sha256, acoustic.audio.frame_count, acoustic.audio.sample_rate_hz, acoustic.audio.channels) != (
                decoded.sha256, decoded.frame_count, decoded.sample_rate_hz, decoded.channels):
            raise ValueError('DECODED_AUDIO_DOMAIN_MISMATCH')
        status['acoustic_evidence_available'] = True
        selected = next(item for item in acoustic.spans if item.original_span.id == span.id)
        result['target_acoustics'] = selected.to_dict()
        if selected.voiced_frame_count == 0:
            result['failure_categories'].append('NO_VOICED_FRAMES')
            result['reason_codes'].append('TARGET_F0_UNAVAILABLE_DURATION_MAY_REMAIN_AVAILABLE')
        stage = 'NORMALIZATION_FAILURE'
        rate = measure_utterance_rate(validated.alignment, validated.mora_count)
        duration = normalize_duration(validated.span, rate)
        result['rate_context'] = rate.to_dict(); result['duration'] = asdict(duration)
        status['normalized_duration_available'] = True
        stage = 'DEVIATION_ABSTENTION'
        reference_validation(reference)
        verify(base['reference_profile']); verify(base['reference_manifest'])
        if asdict(reference.profile_artifact) != base['reference_profile'] or reference.profile.manifest.source != base['reference_manifest']['path']:
            raise ValueError('REFERENCE_OBJECT_DIFFERS_FROM_FROZEN_PLAN')
        p = reference.profile
        if (identity != p.manifest.target or base['prompt_id'] != p.manifest.prompt_id
                or context.transcript_sha256 != p.manifest.transcript_sha256):
            raise ValueError('PROMPT_TARGET_OR_TRANSCRIPT_REFERENCE_MISMATCH')
        if result['sources']['audio']['sha256'] in {dict(take.entry.sources)['audio'].sha256
            for speaker in p.speakers for take in speaker.takes}:
            audio_overlap = True
        else:
            audio_overlap = False
        result['deviation'] = {'representation': 'CONTROLLED_STRESS_DESCRIPTIVE_DURATION_EVIDENCE',
            'interpretation': 'ENGINEERING_RESPONSE_ONLY', 'formulas': FORMULAS,
            'features': {key: describe_duration(getattr(duration, key), dict(p.statistics)[key]) for key in FEATURES},
            'reference_profile': base['reference_profile'], 'reference_manifest': base['reference_manifest'],
            'reference_n': len(p.speakers), 'candidate_speaker_in_reference': base['speaker_id'] in {s.speaker_id for s in p.speakers},
            'candidate_audio_in_reference': audio_overlap,
            'comparison_policy': 'IN_POPULATION_CONTROLLED_NATIVE_STRESS_COMPARISON_NOT_INDEPENDENT_EVALUATION',
            'reference_export_allowed': False}
        status['deviation_evidence_available'] = True
        result['final_status'] = 'EVIDENCE_AVAILABLE'
    except (OSError, ValueError, RuntimeError, KeyError, IndexError, TypeError, AttributeError, ArithmeticError) as error:
        result['final_status'] = 'ABSTAIN'
        result['failure_categories'].append(stage)
        result['reason_codes'].append(str(error))
    save(folder / 'pipeline-result.json', result)
    return result
