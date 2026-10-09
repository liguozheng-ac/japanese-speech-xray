"""External research material is a smoke source, never newly consented collection."""

from pathlib import Path

from speech_xray.reference.manifest import load_manifest
from speech_xray.reference.profile_builder import build_reference_profile
from speech_xray.reference.models import ReferencePolicy
from .batch_plan import digest
from .models import SourceType
from .validation import read_json


def inspect_external_sets(manifest,policy=ReferencePolicy()):
    results=[]
    for reference_path,reference_hash,inventory_path,inventory_hash in manifest.external_reference_sets:
        try:
            if digest(reference_path)!=reference_hash or digest(inventory_path)!=inventory_hash:
                raise ValueError("EXTERNAL_SOURCE_HASH_MISMATCH")
            reference=load_manifest(reference_path)
            inventory,_=read_json(Path(inventory_path))
            if dict(reference.dataset)["local_only"] is not True:
                raise ValueError("EXTERNAL_LOCAL_USE_PROVENANCE_REQUIRED")
            profile=build_reference_profile(reference,policy)
            results.append({"source_type":SourceType.EXTERNAL_RESEARCH_CORPUS,"counts_toward_controlled_readiness":False,
                            "reference_manifest_sha256":reference_hash,"inventory_sha256":inventory_hash,
                            "available_local_speaker_count":len(inventory["speakers"]),
                            "available_local_utterance_count":inventory["utterance_count"],
                            "same_target_independent_speaker_count":len(profile.speakers),
                            "reference_profile_status":profile.profile_status,"rejected_take_count":len(profile.rejected),
                            "usage_restrictions":dict(reference.dataset)["usage_restrictions"]})
        except (OSError,ValueError,KeyError,TypeError):
            results.append({"source_type":SourceType.EXTERNAL_RESEARCH_CORPUS,"counts_toward_controlled_readiness":False,
                            "status":"EXTERNAL_SMOKE_INTEGRITY_FAILURE"})
    return results
