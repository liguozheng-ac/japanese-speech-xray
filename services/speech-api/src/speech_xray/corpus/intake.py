"""Validate a private corpus before analysis; retain every recording outcome."""

from collections import Counter
from dataclasses import replace
from pathlib import Path
import re

from .audio_validation import inspect_audio
from .models import CorpusManifest, IntakeOutcome, Recording, RecordingStatus as Status, SourceType
from .speaker_manifest import session_from_json, speaker_from_json
from .validation import PRIVATE_ROOT, identifier, integer, keys, pinned_json, private_path, read_json, sha256, text


def load_corpus_manifest(path):
    path = Path(path).resolve()
    if not path.is_relative_to(PRIVATE_ROOT.resolve()):
        raise ValueError("CORPUS_MANIFEST_MUST_BE_PRIVATE")
    value, digest = read_json(path)
    keys(value, ("schema_version", "corpus_id", "corpus_root", "prompt_pack", "speaker_manifests", "session_manifests",
                 "recordings", "external_reference_sets", "creation_label"))
    if value["schema_version"] != "0.1":
        raise ValueError("UNSUPPORTED_CORPUS_SCHEMA")
    text(value["creation_label"], "creation label")
    root = private_path(value["corpus_root"], path.parent, PRIVATE_ROOT)
    keys(value["prompt_pack"], ("prompt_pack_id", "prompt_pack_version", "manifest_sha256"))
    pack = value["prompt_pack"]
    for name in ("speaker_manifests", "session_manifests", "recordings", "external_reference_sets"):
        if not isinstance(value[name], list):
            raise ValueError("CORPUS_COLLECTION_MUST_BE_ARRAY")
    speakers, sessions, sources = [], [], []
    for refs, model, destination in ((value["speaker_manifests"], speaker_from_json, speakers),
                                    (value["session_manifests"], session_from_json, sessions)):
        for ref in refs:
            payload, source, source_hash = pinned_json(ref, path.parent, root)
            destination.append(model(payload))
            sources.append((source, source_hash))
    if len({s.speaker_id for s in speakers}) != len(speakers) or len({s.session_id for s in sessions}) != len(sessions):
        raise ValueError("DUPLICATE_SPEAKER_OR_SESSION_MANIFEST")
    recordings = []
    for item in value["recordings"]:
        keys(item, ("speaker_id", "session_id", "prompt_id", "take_id", "source_type", "audio", "evidence_receipt"))
        keys(item["audio"], ("path", "sha256"))
        expected = sha256(item["audio"]["sha256"]) if item["audio"]["sha256"] is not None else None
        audio = private_path(item["audio"]["path"], path.parent, root)
        receipt, receipt_hash = None, None
        if item["evidence_receipt"] is not None:
            keys(item["evidence_receipt"], ("path", "sha256"))
            receipt = str(private_path(item["evidence_receipt"]["path"], path.parent, root))
            receipt_hash = sha256(item["evidence_receipt"]["sha256"])
        recordings.append(Recording(*(identifier(item[name]) for name in ("speaker_id", "session_id", "prompt_id", "take_id")),
                                    SourceType(item["source_type"]), str(audio), expected, receipt, receipt_hash))
    external = []
    for item in value["external_reference_sets"]:
        keys(item, ("source_type", "reference_manifest", "inventory"))
        if item["source_type"] != SourceType.EXTERNAL_RESEARCH_CORPUS:
            raise ValueError("EXTERNAL_SET_MUST_PRESERVE_EXTERNAL_CLASSIFICATION")
        paths = []
        for name in ("reference_manifest", "inventory"):
            keys(item[name], ("path", "sha256"))
            paths += [str(private_path(item[name]["path"], path.parent, PRIVATE_ROOT)), sha256(item[name]["sha256"])]
        external.append(tuple(paths))
    return CorpusManifest(identifier(value["corpus_id"]), str(root), identifier(pack["prompt_pack_id"]),
                          integer(pack["prompt_pack_version"], "pack version"), sha256(pack["manifest_sha256"]),
                          tuple(sorted(speakers, key=lambda s:s.speaker_id)), tuple(sorted(sessions, key=lambda s:s.session_id)),
                          tuple(sorted(recordings, key=lambda r:(r.key,r.session_id))), tuple(sorted(external)), str(path), digest, tuple(sorted(sources)))


def validate_corpus(manifest, pack):
    speakers, sessions = {s.speaker_id:s for s in manifest.speakers}, {s.session_id:s for s in manifest.sessions}
    prompts = {p.prompt_id:p for p in pack.prompts}
    keys_count = Counter(recording.key for recording in manifest.recordings)
    outcomes = []
    pack_matches = (manifest.prompt_pack_id, manifest.prompt_pack_version, manifest.prompt_pack_sha256) == (
                    pack.prompt_pack_id, pack.prompt_pack_version, pack.sha256)
    for recording in manifest.recordings:
        reasons=[]
        speaker, session = speakers.get(recording.speaker_id), sessions.get(recording.session_id)
        if not pack_matches:
            reasons.append("PROMPT_PACK_BINDING_MISMATCH")
        if recording.prompt_id not in prompts:
            reasons.append("UNKNOWN_PROMPT")
        if not re.fullmatch(r"take-[0-9]{2,4}", recording.take_id) or int(recording.take_id.split('-')[-1]) < 1:
            reasons.append("INVALID_TAKE_ID")
        if keys_count[recording.key]>1:
            reasons.append("DUPLICATE_SPEAKER_PROMPT_TAKE")
        if not speaker:
            reasons.append("UNKNOWN_SPEAKER")
        elif speaker.source_type != recording.source_type:
            reasons.append("SOURCE_TYPE_MISMATCH")
        if not session or session.speaker_id != recording.speaker_id:
            reasons.append("UNKNOWN_OR_CONFLICTING_SESSION")
        elif (session.prompt_pack_id,session.prompt_pack_version,session.prompt_pack_sha256) != (pack.prompt_pack_id,pack.prompt_pack_version,pack.sha256):
            reasons.append("SESSION_PROMPT_PACK_MISMATCH")
        if Path(recording.audio_path).name != recording.key+'.wav':
            reasons.append("NONCANONICAL_PSEUDONYMOUS_FILENAME")
        if recording.source_type == SourceType.REAL_REFERENCE_RECORDING:
            if not speaker or speaker.self_reported_native_japanese is not True or speaker.native_status_metadata_status != "PARTICIPANT_SUPPLIED":
                reasons.append("NATIVE_STATUS_MISSING_OR_UNVERIFIED")
            if (not session or session.consent_metadata_status != "PARTICIPANT_SUPPLIED" or not session.consent_record_id
                    or session.permission_local_analysis is not True or session.permission_derived_numeric_features is not True):
                reasons.append("REQUIRED_ANALYSIS_FEATURE_CONSENT_MISSING_OR_UNVERIFIED")
        elif recording.source_type == SourceType.SYNTHETIC_AUDIO:
            reasons.append("SYNTHETIC_AUDIO_NOT_ACCEPTED_FOR_REFERENCE_COLLECTION")
        elif recording.source_type == SourceType.EXTERNAL_RESEARCH_CORPUS:
            reasons.append("USE_EXTERNAL_REFERENCE_SET_ADAPTER_NOT_CONTROLLED_COLLECTION")
        audio, audio_hash, audio_reason = inspect_audio(recording.audio_path)
        if audio_reason:
            reasons.append(audio_reason)
        if recording.expected_audio_sha256 and audio_hash != recording.expected_audio_sha256:
            reasons.append("DECLARED_AUDIO_HASH_MISMATCH")
        valid = not reasons
        outcomes.append(IntakeOutcome(recording, Status.VALIDATED if valid else Status.REJECTED_INTAKE,
                                      tuple(reasons), audio, audio_hash, valid and recording.source_type == SourceType.REAL_REFERENCE_RECORDING))
    hashes = Counter(item.audio_sha256 for item in outcomes if item.audio_sha256)
    return tuple(replace(item, status=Status.REJECTED_INTAKE, reasons=(*item.reasons,"DUPLICATE_EXACT_AUDIO_HASH"),eligible_real_reference=False)
                 if item.audio_sha256 and hashes[item.audio_sha256]>1 else item for item in outcomes)
