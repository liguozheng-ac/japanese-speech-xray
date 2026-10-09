"""Adapters reusing upstream validation, normalization and reference construction."""
from pathlib import Path
from speech_xray.reference.integrity import validate_entry
from speech_xray.reference.speech_rate import measure_utterance_rate
from speech_xray.reference.normalization import normalize_duration
from speech_xray.reference.manifest import load_manifest
from speech_xray.reference.profile_builder import build_reference_profile
from speech_xray.reference.models import ArtifactReference
from speech_xray.corpus.batch_plan import digest
from .models import CandidateObservation, ReferenceObservation


def candidate_from_bundle(manifest, entry):
    source = validate_entry(manifest, entry)
    rate = measure_utterance_rate(source.alignment, source.mora_count)
    return CandidateObservation(manifest, entry, source.span, rate, normalize_duration(source.span, rate))


def verified_reference(manifest_path, profile_artifact, version):
    if digest(profile_artifact.path) != profile_artifact.sha256:
        raise ValueError('REFERENCE_ARTIFACT_IDENTITY_MISMATCH')
    profile = build_reference_profile(load_manifest(manifest_path))
    if Path(profile_artifact.path).read_text(encoding='utf-8') != profile.to_json():
        raise ValueError('REFERENCE_PROFILE_RECONSTRUCTION_MISMATCH')
    return ReferenceObservation(profile, profile_artifact, version,
                                profile.manifest.reference_set_id, profile_artifact)
