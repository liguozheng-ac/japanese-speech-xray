"""One actual speaker per primary MFA batch, with verified stage-level resume."""

import hashlib
import os
from pathlib import Path
import shutil

from speech_xray.alignment.textgrid_parser import parse_textgrid
from speech_xray.corpus.batch_plan import digest, object_hash, pipeline_configuration, model_resources
from speech_xray.corpus.pipeline import mfa_align, new_text
from speech_xray.corpus.validation import PRIVATE_ROOT, PROJECT_ROOT
from .cache import read_control as read_json, safe_directory
from speech_xray.acoustics.models import evidence_json


def worker_models(root):
    root = safe_directory(root)
    metadata = []
    for resource in model_resources():
        if resource["actual_sha256"] != resource["expected_sha256"]:
            raise ValueError("PINNED_MFA_RESOURCES_REQUIRED")
        origin = PROJECT_ROOT / resource["path"]
        relative = Path(resource["path"]).relative_to(".mfa")
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            with origin.open("rb") as source, target.open("xb") as destination:
                shutil.copyfileobj(source, destination)
        if digest(target) != resource["expected_sha256"]:
            raise ValueError("WORKER_MODEL_IDENTITY_MISMATCH")
        metadata.append({"path": str(target), "sha256": resource["expected_sha256"]})
    os.environ["MFA_ROOT_DIR"] = str(root)
    return metadata


def batch_signature(jobs):
    primary = pipeline_configuration()
    config = {k: primary[k] for k in ("alignment", "reading", "environment_locks", "model_resource_metadata_sha256", "model_resources", "analysis_code_sha256")}
    config["batch_adapter_sha256"] = digest(Path(__file__))
    config["input_policy"] = "ORIGINAL_OFFICIAL_TEXT_NEWLINE_UNCHANGED_WAV_ONE_CORPUS_SPEAKER"
    identity = [{"speaker_id": j["speaker_id"], "prompt_id": j["prompt_id"], "audio_sha256": j["audio_sha256"],
                 "text_sha256": hashlib.sha256((j["text"] + "\n").encode()).hexdigest()} for j in jobs]
    return object_hash({"configuration": config, "utterances": identity}), config


def validated_batch_receipt(path, jobs, signature):
    value, _ = read_json(path)
    if value["signature"] != signature:
        raise ValueError("BATCH_CACHE_CONFIGURATION_MISMATCH")
    for job in jobs:
        if digest(job["audio_path"]) != job["audio_sha256"]:
            raise ValueError("AUDIO_CHANGED_AFTER_INVENTORY")
    for artifact in value["artifacts"]:
        path = Path(artifact["path"]).resolve()
        if not path.is_relative_to(PRIVATE_ROOT.resolve()) or digest(path) != artifact["sha256"]:
            raise ValueError("BATCH_CACHE_ARTIFACT_IDENTITY_MISMATCH")
    expected = {j["prompt_id"] for j in jobs}
    if set(value["results"]) != expected:
        raise ValueError("BATCH_CACHE_UTTERANCE_SET_MISMATCH")
    for result in value["results"].values():
        if result["status"] == "PASS":
            parse_textgrid(Path(result["textgrid"]))
    return value


def align_batch(jobs, output_root, worker_root, aligner=mfa_align):
    jobs = sorted(jobs, key=lambda j: j["prompt_id"])
    if not jobs or len({j["speaker_id"] for j in jobs}) != 1 or len({j["prompt_id"] for j in jobs}) != len(jobs):
        raise ValueError("MFA_BATCH_REQUIRES_DISTINCT_PROMPTS_FROM_ONE_SPEAKER")
    root = safe_directory(output_root)
    signature, config = batch_signature(jobs)
    parent = root / signature
    parent.mkdir(parents=True, exist_ok=True)
    invalid = []
    for previous in sorted(parent.glob("attempt-*/batch-receipt.json")):
        try:
            value = validated_batch_receipt(previous, jobs, signature)
            return {**value, "execution_cache_hit": True}
        except (OSError, ValueError, KeyError, TypeError):
            invalid.append(str(previous))
    models = worker_models(worker_root)
    number = 0
    while (parent / f"attempt-{number:03}").exists():
        number += 1
    folder = parent / f"attempt-{number:03}"
    folder.mkdir()
    prepared = folder / "input"
    prepared.mkdir()
    for job in jobs:
        source = Path(job["audio_path"]).resolve()
        if not source.is_relative_to(PRIVATE_ROOT.resolve()) or digest(source) != job["audio_sha256"]:
            raise ValueError("AUDIO_CHANGED_OR_OUTSIDE_PRIVATE_ROOT")
        stem = job["speaker_id"] + "__" + job["prompt_id"]
        with source.open("rb") as stream, (prepared / (stem + ".wav")).open("xb") as destination:
            shutil.copyfileobj(stream, destination)
        new_text(prepared / (stem + ".lab"), job["text"] + "\n")
    first = jobs[0]
    stem = first["speaker_id"] + "__" + first["prompt_id"]
    paths = {"run_directory": str(folder), "textgrid": str(folder / "aligned" / (stem + ".TextGrid"))}
    failure = None
    try:
        aligner(paths, first)
    except (OSError, ValueError, RuntimeError) as error:
        failure = type(error).__name__
    results = {}
    for job in jobs:
        stem = job["speaker_id"] + "__" + job["prompt_id"]
        grid = folder / "aligned" / (stem + ".TextGrid")
        try:
            parse_textgrid(grid)
            results[job["prompt_id"]] = {"status": "PASS", "textgrid": str(grid),
                "transcript": str(prepared / (stem + ".lab")), "batch_failure": failure}
        except (OSError, ValueError):
            results[job["prompt_id"]] = {"status": "ALIGNMENT_FAILED", "reason": "MFA_ALIGNMENT_DID_NOT_PRODUCE_VALID_OUTPUT",
                "transcript": str(prepared / (stem + ".lab")), "batch_failure": failure}
    artifacts = [{"path": str(p), "sha256": digest(p)} for p in sorted(folder.rglob("*"))
                 if p.is_file() and (p.parent == prepared or p.suffix.lower() == ".textgrid" or p.name == "alignment.log")]
    value = {"schema_version": "0.1", "source_type": first.get("source_type", "EXTERNAL_RESEARCH_CORPUS"), "signature": signature,
             "configuration": config, "speaker_id": first["speaker_id"], "worker_models": models,
             "results": results, "artifacts": artifacts, "invalid_previous_receipts": invalid}
    new_text(folder / "batch-receipt.json", evidence_json(value))
    return {**value, "execution_cache_hit": False}
