"""Hash-pinned manifests use file references, never embedded speech evidence."""

from pathlib import Path
import re

from speech_xray.japanese.models import MappingBasis, VowelClass
from .json_input import read_json
from .models import ArtifactReference, ReferenceEntry, ReferenceManifest, TargetIdentity
from .numeric import integer

PROJECT_ROOT = Path(__file__).resolve().parents[5]
SOURCE_NAMES = ("audio", "alignment", "mora_analysis", "acoustic_evidence", "transcript")


def text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def sha256(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("Expected lowercase SHA-256")
    return value


def keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError("Unexpected reference schema fields")


def load_manifest(path: str | Path, allowed_root: Path = PROJECT_ROOT) -> ReferenceManifest:
    source = Path(path).resolve()
    allowed_root = allowed_root.resolve()
    if not source.is_relative_to(allowed_root):
        raise ValueError("Manifest must remain within this project")
    value, digest = read_json(source)
    keys(value, ("schema_version", "reference_set_id", "prompt_id", "transcript_sha256", "target",
                 "dataset", "creation_metadata", "entries"))
    if value["schema_version"] != "0.1":
        raise ValueError("Expected reference manifest schema 0.1")
    target = value["target"]
    keys(target, ("target_id", "word_index", "word_mora_indices", "phone_label", "vowel_class", "mora_span", "mapping_basis"))
    if not isinstance(target["word_mora_indices"], list):
        raise ValueError("Expected word-local mora index array")
    indices = tuple(integer(index, "word_mora_index") for index in target["word_mora_indices"])
    if len(indices) != 2 or indices[1] != indices[0] + 1 or integer(target["mora_span"], "mora_span") != 2:
        raise ValueError("Target must identify one existing two-mora long-vowel span")
    identity = TargetIdentity(text(target["target_id"], "target_id"), integer(target["word_index"], "word_index"),
                              indices, text(target["phone_label"], "phone_label"),
                              VowelClass(target["vowel_class"]).value, 2, MappingBasis(target["mapping_basis"]).value)
    dataset = value["dataset"]
    keys(dataset, ("name", "source", "local_only", "usage_restrictions", "material_kind"))
    for name in ("name", "source", "usage_restrictions"):
        text(dataset[name], name)
    if type(dataset["local_only"]) is not bool or dataset["material_kind"] not in {
            "REAL_REFERENCE_AUDIO", "STRUCTURED_REFERENCE_FIXTURE"}:
        raise ValueError("Invalid dataset provenance")
    keys(value["creation_metadata"], ("label",))
    label = text(value["creation_metadata"]["label"], "creation label")
    if not isinstance(value["entries"], list):
        raise ValueError("Entries must be an array")
    entries, take_keys = [], set()
    for item in value["entries"]:
        keys(item, ("prompt_id", "target_id", "speaker_id", "take_id", "utterance_id", "span_id", "sources"))
        for name in ("prompt_id", "target_id", "speaker_id", "take_id", "utterance_id", "span_id"):
            text(item[name], name)
        pair = (item["speaker_id"], item["take_id"])
        if pair in take_keys:
            raise ValueError("Duplicate speaker/take identity")
        take_keys.add(pair)
        keys(item["sources"], SOURCE_NAMES)
        refs = []
        for name in SOURCE_NAMES:
            ref = item["sources"][name]
            keys(ref, ("path", "sha256"))
            path_value = Path(text(ref["path"], "source path"))
            resolved = (source.parent / path_value).resolve()
            if not resolved.is_relative_to(allowed_root):
                raise ValueError("Artifact paths must remain within this project")
            refs.append((name, ArtifactReference(str(resolved), sha256(ref["sha256"]))))
        entries.append(ReferenceEntry(*(item[name] for name in
                         ("prompt_id", "target_id", "speaker_id", "take_id", "utterance_id", "span_id")), tuple(refs)))
    return ReferenceManifest(text(value["reference_set_id"], "reference_set_id"), text(value["prompt_id"], "prompt_id"),
                             sha256(value["transcript_sha256"]), identity, tuple(sorted(dataset.items())), label,
                             tuple(sorted(entries, key=lambda entry: (entry.speaker_id, entry.take_id))), str(source), digest)
