"""Validate both evidence inputs before any descriptive comparison."""
from pathlib import Path
from decimal import Decimal
from speech_xray.reference.integrity import validate_entry
from speech_xray.reference.models import ProfileStatus, ReferencePolicy
from speech_xray.reference.manifest import load_manifest, sha256, PROJECT_ROOT
from speech_xray.reference.json_input import read_json
from speech_xray.reference.profile_builder import FEATURES as PROFILE_FEATURES, take_features
from speech_xray.reference.robust_stats import summarize
from speech_xray.reference.normalization import normalize_duration
from speech_xray.reference.speech_rate import measure_utterance_rate
from speech_xray.corpus.batch_plan import digest
from .models import CandidateObservation, ReferenceObservation, EvidenceStatus as S
from .duration import FEATURES


class Abstention(ValueError):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status = status


def check(condition, status, reason):
    if not condition:
        raise Abstention(status, reason)


def positive(value):
    return isinstance(value, Decimal) and value.is_finite() and value > 0


def candidate_validation(candidate):
    status = S.ABSTAIN_INVALID_CANDIDATE
    check(isinstance(candidate, CandidateObservation), status, 'CANDIDATE_TYPE_INVALID')
    check(candidate.duration is not None, S.ABSTAIN_MISSING_NORMALIZED_DURATION, 'NORMALIZED_DURATION_MISSING')
    check(candidate.duration.rate_normalized_duration is not None,
          S.ABSTAIN_MISSING_NORMALIZED_DURATION, 'NORMALIZED_DURATION_MISSING')
    check(all(positive(getattr(candidate.duration, key)) for key in FEATURES), status, 'CANDIDATE_DURATION_INVALID')
    check(candidate.entry in candidate.manifest.entries, status, 'CANDIDATE_NOT_IN_SOURCE_MANIFEST')
    check(candidate.original_span.mora_span == candidate.manifest.target.mora_span == 2,
          S.ABSTAIN_TARGET_MISMATCH, 'CANDIDATE_MORA_SPAN_MISMATCH')
    check(digest(candidate.manifest.source) == candidate.manifest.sha256, status, 'CANDIDATE_MANIFEST_CHANGED')
    check(load_manifest(candidate.manifest.source) == candidate.manifest, status, 'CANDIDATE_CONTEXT_ARTIFACT_MISMATCH')
    source = validate_entry(candidate.manifest, candidate.entry)
    rate = measure_utterance_rate(source.alignment, source.mora_count)
    check(candidate.original_span == source.span and candidate.rate == rate,
          status, 'CANDIDATE_TIMING_OR_RATE_PROVENANCE_MISMATCH')
    check(candidate.duration == normalize_duration(source.span, rate), status, 'CANDIDATE_NORMALIZATION_MISMATCH')


def reference_validation(reference):
    status = S.ABSTAIN_INVALID_REFERENCE
    check(isinstance(reference, ReferenceObservation), status, 'REFERENCE_TYPE_INVALID')
    p = reference.profile
    check(p.profile_status == ProfileStatus.READY_FOR_EXPERIMENT,
          S.ABSTAIN_REFERENCE_NOT_READY, 'REFERENCE_PROFILE_NOT_READY')
    check(not p.rejected and len(p.speakers) >= max(p.policy.minimum_independent_speakers,
          ReferencePolicy().minimum_independent_speakers), S.ABSTAIN_REFERENCE_NOT_READY, 'REFERENCE_N_NOT_READY')
    check(p.manifest.target.mora_span == 2, status, 'REFERENCE_MORA_SPAN_INVALID')
    check(isinstance(reference.version, str) and bool(reference.version), status, 'REFERENCE_VERSION_MISSING')
    real = dict(p.manifest.dataset)['material_kind'] == 'REAL_REFERENCE_AUDIO'
    if real:
        check(reference.version == 'task009-v2' and reference.origin_reference_set_id.startswith('task009-v2-')
              and (p.manifest.reference_set_id == reference.origin_reference_set_id
                   or p.manifest.reference_set_id.startswith(reference.origin_reference_set_id+'/loo/')),
              status, 'REFERENCE_VERSION_NOT_ACTIVE')
    for artifact in (reference.profile_artifact, reference.origin_profile_artifact):
        check(Path(artifact.path).resolve().is_relative_to(PROJECT_ROOT.resolve()),status,'REFERENCE_ARTIFACT_OUTSIDE_PROJECT')
        sha256(artifact.sha256)
        check(digest(artifact.path) == artifact.sha256, status, 'REFERENCE_ARTIFACT_CHANGED')
    origin,_ = read_json(Path(reference.origin_profile_artifact.path))
    check(origin['reference_set_id'] == reference.origin_reference_set_id
          and origin['target'] == p.manifest.target.to_dict()
          and origin['prompt_id'] == p.manifest.prompt_id
          and origin['normalization'] == p.to_dict()['normalization'],
          status,'REFERENCE_ORIGIN_IDENTITY_OR_FEATURE_MISMATCH')
    check(load_manifest(p.manifest.source) == p.manifest,status,'REFERENCE_CONTEXT_ARTIFACT_MISMATCH')
    check(digest(p.manifest.source) == p.manifest.sha256, status, 'REFERENCE_MANIFEST_CHANGED')
    check(Path(reference.profile_artifact.path).read_text(encoding='utf-8') == p.to_json(),
          status, 'REFERENCE_OBJECT_ARTIFACT_MISMATCH')
    ids = [speaker.speaker_id for speaker in p.speakers]
    check(len(set(ids)) == len(ids), status, 'REFERENCE_SPEAKER_DUPLICATE')
    entries = [take.entry for speaker in p.speakers for take in speaker.takes]
    check(sorted(entries, key=lambda e:(e.speaker_id,e.take_id)) == list(p.manifest.entries),
          status, 'REFERENCE_OBSERVATION_MEMBERSHIP_MISMATCH')
    audio = [dict(entry.sources)['audio'].sha256 for entry in entries]
    check(len(set(audio)) == len(audio), status, 'REFERENCE_AUDIO_DUPLICATE')
    stats = dict(p.statistics)
    check(set(stats) == set(PROFILE_FEATURES), status, 'REFERENCE_FEATURE_DEFINITION_MISMATCH')
    for speaker in p.speakers:
        check(bool(speaker.takes), status, 'REFERENCE_EMPTY_SPEAKER')
        for take in speaker.takes:
            check(take.entry.speaker_id == speaker.speaker_id
                  and take.entry.target_id == p.manifest.target.target_id
                  and take.entry.prompt_id == p.manifest.prompt_id
                  and take.reference_set_id == p.manifest.reference_set_id,
                  status, 'REFERENCE_TAKE_IDENTITY_MISMATCH')
            check(take.duration == normalize_duration(take.original_span, take.rate), status, 'REFERENCE_NORMALIZATION_MISMATCH')
        medians = tuple((key,summarize(take_features(t)[key] for t in speaker.takes).median) for key in PROFILE_FEATURES)
        check(speaker.medians == medians, status, 'REFERENCE_SPEAKER_AGGREGATION_MISMATCH')
    for key, stat in p.statistics:
        values = (stat.minimum,stat.q25,stat.median,stat.q75,stat.maximum,stat.mad,stat.iqr)
        check(all(isinstance(v,Decimal) and v.is_finite() for v in values), status, 'REFERENCE_STATISTICS_NONFINITE')
        check(stat.count == len(ids) and stat.minimum <= stat.q25 <= stat.median <= stat.q75 <= stat.maximum
              and stat.mad >= 0 and stat.iqr >= 0, status, 'REFERENCE_STATISTICS_ORDER_OR_N_INVALID')
        if key in FEATURES:
            check(stat.minimum > 0, status, 'REFERENCE_DURATION_NONPOSITIVE')
        check(stat == summarize(dict(s.medians)[key] for s in p.speakers), status, 'REFERENCE_STATISTICS_RECONSTRUCTION_MISMATCH')


def paired_validation(candidate, reference):
    p = reference.profile
    check(candidate.manifest.prompt_id == p.manifest.prompt_id and candidate.manifest.target == p.manifest.target,
          S.ABSTAIN_TARGET_MISMATCH, 'PROMPT_OR_TARGET_IDENTITY_MISMATCH')
    check(candidate.manifest.transcript_sha256 == p.manifest.transcript_sha256,
          S.ABSTAIN_TARGET_MISMATCH, 'PROMPT_TRANSCRIPT_IDENTITY_MISMATCH')
    check(candidate.entry.speaker_id not in {s.speaker_id for s in p.speakers},
          S.ABSTAIN_REFERENCE_LEAKAGE, 'CANDIDATE_SPEAKER_INCLUDED_IN_REFERENCE')
    check(dict(candidate.entry.sources)['audio'].sha256 not in {
        dict(t.entry.sources)['audio'].sha256 for s in p.speakers for t in s.takes},
        S.ABSTAIN_REFERENCE_LEAKAGE, 'CANDIDATE_AUDIO_INCLUDED_IN_REFERENCE')
