"""Validate accepted recommendation lineage without rewriting historical data."""

from pathlib import Path
from .cache import read_control as read_json
from speech_xray.corpus.batch_plan import digest, object_hash, pipeline_configuration
from speech_xray.external_jvs.inventory import PRIVATE_ROOT, private_root

BASELINE = "872bcedeccc88584be66e6a0653070925a4bd4eb"
DEFERRED = frozenset({
    "jvs-parallel100-voiceactress100_040-w004-m000",
    "jvs-parallel100-voiceactress100_099-w001-m000",
    "jvs-parallel100-voiceactress100_049-w008-m000",
})


def load_inputs(source_root):
    root = private_root(source_root)
    audit_path = root / "reports/full-audit-v1.json"
    smoke_path = root / "reports/full-smoke-v2.json"
    receipt_path = root / "source/extraction-receipt.json"
    audit, audit_hash = read_json(audit_path)
    smoke, smoke_hash = read_json(smoke_path)
    receipt, receipt_hash = read_json(receipt_path)
    selection = smoke["reviewed_recommendation"]
    initial = audit["recommendation"]["selected_targets"]
    final = selection["selected_targets"]
    deferred = selection["deferred_targets"]
    initial_ids = {t["target_id"] for t in initial}
    final_ids = {t["target_id"] for t in final}
    deferred_ids = {t["target_id"] for t in deferred}
    replacements = [t for t in final if "replaces_deferred_target_id" in t]
    if (len(initial) != 20 or len(initial_ids) != 20 or len(final) != 19 or len(final_ids) != 19
            or deferred_ids != DEFERRED or len(deferred) != 3
            or len(replacements) != 2 or final_ids & deferred_ids
            or initial_ids - deferred_ids | {t["target_id"] for t in replacements} != final_ids):
        raise ValueError("ACCEPTED_TARGET_LINEAGE_MISMATCH")
    for target in replacements:
        previous = next(t for t in deferred if t["target_id"] == target["replaces_deferred_target_id"])
        if (target["orthographic_pattern"], target["vowel_class"]) != (previous["orthographic_pattern"], previous["vowel_class"]):
            raise ValueError("REPLACEMENT_PATTERN_OR_CLASS_MISMATCH")
    if audit["inventory"]["source_type"] != "EXTERNAL_RESEARCH_CORPUS" or smoke["source_type"] != "EXTERNAL_RESEARCH_CORPUS":
        raise ValueError("EXTERNAL_SOURCE_CLASSIFICATION_REQUIRED")
    corpus_root = private_root(audit["inventory"]["corpus_root"])
    for ref in audit["inventory"]["transcript_sources"]:
        if digest(ref["path"]) != ref["sha256"]:
            raise ValueError("TRANSCRIPT_CHANGED_SINCE_ACCEPTED_AUDIT")
    current = pipeline_configuration()
    for key in ("alignment", "reading", "environment_locks", "model_resource_metadata_sha256", "model_resources", "analysis_code_sha256", "acoustics"):
        if current[key] != smoke["configuration"][key]:
            raise ValueError("ACCEPTED_PIPELINE_CONFIGURATION_CHANGED:" + key)
    # A streaming ZIP identity check avoids loading the several-GB archive at once.
    import hashlib
    archive = Path(receipt["archive_path"]).resolve()
    if not archive.is_relative_to(PRIVATE_ROOT.resolve()):
        raise ValueError("ARCHIVE_PATH_MUST_REMAIN_PRIVATE")
    hasher = hashlib.sha256()
    with archive.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            hasher.update(block)
    if hasher.hexdigest() != receipt["archive_sha256"]:
        raise ValueError("ARCHIVE_CHANGED_SINCE_ACCEPTED_EXTRACTION")
    lineage = {"baseline_commit": BASELINE, "source_type": "EXTERNAL_RESEARCH_CORPUS",
               "initial_target_ids": sorted(initial_ids), "deferred_target_ids": sorted(deferred_ids),
               "replacements": [{"target_id": t["target_id"], "replaces": t["replaces_deferred_target_id"]} for t in replacements],
               "final_target_ids": sorted(final_ids), "arithmetic": "20 - 3 + 2 = 19",
               "distinct_reviewed_target_ids": len(initial_ids | final_ids),
               "source_artifacts": {"audit": audit_hash, "smoke": smoke_hash, "extraction_receipt": receipt_hash},
               "target_set_sha256": object_hash(sorted(final, key=lambda t: t["target_id"])),
               "archive_sha256": receipt["archive_sha256"]}
    return {"inventory": audit["inventory"], "discovery": audit["discovery"], "targets": final,
            "smoke": smoke, "lineage": lineage, "corpus_root": str(corpus_root)}
