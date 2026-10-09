"""Participant assertions and permissions remain explicit, private metadata."""

from .models import Session, SourceType, Speaker
from .validation import boolean_or_missing, identifier, integer, keys, sha256, text


def speaker_from_json(value):
    keys(value, ("schema_version", "speaker_id", "source_type", "self_reported_native_japanese", "native_status_metadata_status"))
    if value["schema_version"] != "0.1" or value["native_status_metadata_status"] not in {"PARTICIPANT_SUPPLIED", "UNVERIFIED", "TEST_ASSERTION"}:
        raise ValueError("INVALID_SPEAKER_SCHEMA")
    return Speaker(identifier(value["speaker_id"]), SourceType(value["source_type"]),
                   boolean_or_missing(value["self_reported_native_japanese"]), value["native_status_metadata_status"])


def session_from_json(value):
    required = {"schema_version", "session_id", "speaker_id", "prompt_pack_id", "prompt_pack_version", "prompt_pack_sha256",
                "consent_record_id", "consent_metadata_status", "permission_local_analysis", "permission_derived_numeric_features",
                "recording_date_label", "recording_environment_label"}
    optional = {"permission_public_raw_audio", "permission_public_aggregate_statistics"}
    if not isinstance(value, dict) or not required <= set(value) <= required | optional:
        raise ValueError("INVALID_SESSION_SCHEMA")
    if value["schema_version"] != "0.1" or value["consent_metadata_status"] not in {"PARTICIPANT_SUPPLIED", "UNVERIFIED", "TEST_ASSERTION"}:
        raise ValueError("INVALID_CONSENT_METADATA_STATUS")
    if value["consent_record_id"] is not None:
        identifier(value["consent_record_id"])
    for name in ("recording_date_label", "recording_environment_label"):
        text(value[name], name)
    public_audio, public_stats = value.get("permission_public_raw_audio", False), value.get("permission_public_aggregate_statistics", False)
    if type(public_audio) is not bool or type(public_stats) is not bool:
        raise ValueError("PUBLIC_PERMISSION_MUST_BE_EXPLICIT_BOOLEAN")
    return Session(identifier(value["session_id"]), identifier(value["speaker_id"]), identifier(value["prompt_pack_id"]),
                   integer(value["prompt_pack_version"], "pack version"), sha256(value["prompt_pack_sha256"]),
                   value["consent_record_id"], value["consent_metadata_status"],
                   boolean_or_missing(value["permission_local_analysis"]), boolean_or_missing(value["permission_derived_numeric_features"]),
                   public_audio, public_stats)
