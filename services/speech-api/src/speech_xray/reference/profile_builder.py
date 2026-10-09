"""Reference evidence only: validate takes, aggregate speakers, summarize speakers."""

from collections import defaultdict
from importlib.metadata import version
import platform

from .integrity import IntegrityError, validate_entry
from .models import (ProfileStatus as Status, ReferencePolicy, ReferenceProfile,
                     RejectedObservation, SpeakerReferenceObservation, TakeReferenceObservation)
from .normalization import normalize_duration
from .robust_stats import summarize
from .speech_rate import measure_utterance_rate

FEATURES = ("raw_duration_ms", "utterance_mora_rate_per_second", "mean_mora_period_ms",
            "rate_normalized_duration", "rate_normalized_duration_per_mora")


def take_features(take):
    return {"raw_duration_ms": take.duration.raw_duration_ms,
            "utterance_mora_rate_per_second": take.rate.utterance_mora_rate_per_second,
            "mean_mora_period_ms": take.rate.mean_mora_period_ms,
            "rate_normalized_duration": take.duration.rate_normalized_duration,
            "rate_normalized_duration_per_mora": take.duration.rate_normalized_duration_per_mora}


def build_reference_profile(manifest, policy: ReferencePolicy = ReferencePolicy()) -> ReferenceProfile:
    grouped, rejected = defaultdict(list), []
    audio_occurrences = defaultdict(list)
    for entry in manifest.entries:
        audio_occurrences[dict(entry.sources)["audio"].sha256].append(entry)
    for entry in sorted(manifest.entries, key=lambda item: (item.speaker_id, item.take_id)):
        try:
            if len(audio_occurrences[dict(entry.sources)["audio"].sha256]) > 1:
                raise IntegrityError("DUPLICATE_AUDIO_OBSERVATION_NOT_INDEPENDENT")
            source = validate_entry(manifest, entry)
            try:
                rate = measure_utterance_rate(source.alignment, source.mora_count)
                duration = normalize_duration(source.span, rate)
            except ValueError as error:
                raise IntegrityError("INVALID_UTTERANCE_RATE", Status.INVALID_RATE_CONTEXT) from error
            grouped[entry.speaker_id].append(TakeReferenceObservation(manifest.reference_set_id, entry,
                                                                     source.span, rate, duration))
        except IntegrityError as error:
            rejected.append(RejectedObservation(entry, error.status, str(error)))
    speakers = []
    for speaker_id, takes in sorted(grouped.items()):
        features = [take_features(take) for take in takes]
        medians = tuple((key, summarize(item[key] for item in features).median) for key in FEATURES)
        speakers.append(SpeakerReferenceObservation(speaker_id, tuple(takes), medians))
    stats = tuple((key, summarize(dict(speaker.medians)[key] for speaker in speakers)) for key in FEATURES)
    warnings = ["EXPERIMENTAL_REFERENCE_SAMPLE_NOT_POPULATION_NORM",
                "SPEAKER_IDS_AND_PROMPT_ASSIGNMENTS_REQUIRE_TRUSTED_SOURCE_METADATA",
                "INTERNAL_PAUSES_INCLUDED_IN_UTTERANCE_RATE"]
    if rejected:
        # Fail closed even if the remaining subset would satisfy speaker policy.
        statuses = {item.status for item in rejected}
        status = next(item for item in (Status.PROMPT_MISMATCH, Status.TARGET_MISMATCH,
                                       Status.INTEGRITY_FAILURE, Status.INVALID_RATE_CONTEXT) if item in statuses)
        warnings.append("REJECTED_OBSERVATIONS_PRESENT_PROFILE_NOT_READY")
    elif not speakers:
        status = Status.NO_VALID_OBSERVATIONS
    elif len(speakers) < policy.minimum_independent_speakers:
        status = Status.INSUFFICIENT_SPEAKERS
        warnings.append("INDEPENDENT_SPEAKER_COUNT_BELOW_PROJECT_POLICY")
    else:
        status = Status.READY_FOR_EXPERIMENT
    if dict(manifest.dataset)["material_kind"] == "STRUCTURED_REFERENCE_FIXTURE":
        warnings.append("STRUCTURED_MATHEMATICAL_FIXTURE_NOT_HUMAN_REFERENCE_SPEECH")
    versions = (("python", platform.python_version()), ("numpy", version("numpy")))
    return ReferenceProfile(manifest, policy, tuple(speakers), stats, tuple(rejected), status, versions, tuple(warnings))
