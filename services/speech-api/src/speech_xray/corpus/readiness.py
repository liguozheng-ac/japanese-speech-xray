"""Eligible real recordings, target-specific integrity and speaker independence."""

from collections import Counter,defaultdict
from dataclasses import replace
from pathlib import Path
import hashlib

from speech_xray.reference.models import ReferencePolicy
from speech_xray.reference.profile_builder import build_reference_profile
from speech_xray.acoustics.models import evidence_json
from .batch_plan import model_resources
from .external import inspect_external_sets
from .integrity import reference_manifest
from .models import RecordingStatus as Status,SourceType
from .validation import PROJECT_ROOT


def target_gate(speaker_ids,minimum):
    count=len(set(speaker_ids))
    return {"independent_speaker_count":count,"reference_profile_status":"READY_FOR_EXPERIMENT" if count>=minimum else "INSUFFICIENT_SPEAKERS"}


def dataset_level(tooling_ready,ready_targets,total_targets,real_recordings):
    if not tooling_ready:
        return "TOOLING_NOT_READY"
    if total_targets and ready_targets==total_targets:
        return "REFERENCE_DATA_READY"
    if ready_targets:
        return "REFERENCE_TARGETS_PARTIALLY_READY"
    if real_recordings:
        return "REAL_DATA_PRESENT_INSUFFICIENT"
    return "TOOLING_READY_NO_REAL_DATA"


def reference_input_value(profile):
    manifest=profile.manifest
    return {"schema_version":"0.1","reference_set_id":manifest.reference_set_id,"prompt_id":manifest.prompt_id,
            "transcript_sha256":manifest.transcript_sha256,"target":manifest.target.to_dict(),"dataset":dict(manifest.dataset),
            "creation_metadata":{"label":manifest.creation_label},"entries":[entry.to_dict() for entry in manifest.entries]}


def build_readiness(manifest,pack,outcomes,jobs,qa,policy=ReferencePolicy()):
    grouped=defaultdict(list)
    for job in jobs:
        item=job.intake
        # Repeat the firewall here, independently of intake's cached boolean.
        if (item.status!=Status.VALIDATED or not item.eligible_real_reference
                or item.recording.source_type!=SourceType.REAL_REFERENCE_RECORDING):
            continue
        for target in job.targets:
            if target.status==Status.REFERENCE_READY and target.reference_entry and target.target_identity:
                grouped[target.target_id].append((item,target))
    profiles,targets=[],[]
    all_targets=[(prompt,target) for prompt in pack.prompts for target in prompt.targets]
    for prompt,target in all_targets:
        admitted=grouped[target.target_id]
        entries=[outcome.reference_entry for _,outcome in admitted]
        gate=target_gate([entry.speaker_id for entry in entries],policy.minimum_independent_speakers)
        engine_status="NO_VALID_OBSERVATIONS"
        valid_entries=[]
        if entries:
            identity=admitted[0][1].target_identity
            transcript_hash=dict(entries[0].sources)["transcript"].sha256
            ref=reference_manifest(manifest,pack,target,identity,entries,transcript_hash,
                                   manifest.source+"#"+target.target_id,"0"*64)
            profile=build_reference_profile(ref,policy)
            ref=replace(ref,sha256=hashlib.sha256(evidence_json(reference_input_value(profile)).encode()).hexdigest())
            profile=build_reference_profile(ref,policy)
            engine_status=profile.profile_status
            valid_entries=[take.entry for speaker in profile.speakers for take in speaker.takes]
            gate=target_gate([entry.speaker_id for entry in valid_entries],policy.minimum_independent_speakers)
            if profile.rejected:
                gate["reference_profile_status"]=engine_status
            profiles.append(profile)
        targets.append({"prompt_id":prompt.prompt_id,"target_id":target.target_id,**gate,"valid_observation_count":len(valid_entries),
                        "engine_profile_status":engine_status,"orthographic_pattern":target.orthographic_pattern,
                        "candidate_type":target.expected_candidate_type,"vowel_class":target.expected_vowel_class,
                        "speaker_ids":sorted({entry.speaker_id for entry in valid_entries})})
    ready=sum(t["reference_profile_status"]=="READY_FOR_EXPERIMENT" for t in targets)
    real=[item for item in outcomes if item.eligible_real_reference and item.recording.source_type==SourceType.REAL_REFERENCE_RECORDING and item.status==Status.VALIDATED]
    resources=model_resources()
    backend_available=((PROJECT_ROOT/".tools/Library/bin/micromamba.exe").is_file()
                       and (PROJECT_ROOT/".envs/mfa/conda-meta/history").is_file()
                       and all(item["actual_sha256"]==item["expected_sha256"] for item in resources))
    tooling_ready=qa["status"]=="PASS" and backend_available
    level=dataset_level(tooling_ready,ready,len(targets),len(real))
    per_prompt=[]
    speaker_ids=sorted({item.recording.speaker_id for item in outcomes})
    matrix=[]
    for prompt in pack.prompts:
        rows=[t for t in targets if t["prompt_id"]==prompt.prompt_id]
        complete=set.intersection(*(set(row["speaker_ids"]) for row in rows)) if rows else set()
        per_prompt.append({"prompt_id":prompt.prompt_id,"independent_speaker_count":len(complete),
                           "eligible_intake_speaker_count":len({i.recording.speaker_id for i in real if i.recording.prompt_id==prompt.prompt_id}),
                           "ready_target_count":sum(row["reference_profile_status"]=="READY_FOR_EXPERIMENT" for row in rows),"target_count":len(rows)})
        matrix.append({"prompt_id":prompt.prompt_id,"speakers":{speaker:{"complete_target_evidence":speaker in complete,
                         "ready_target_ids":[row["target_id"] for row in rows if speaker in row["speaker_ids"]],
                         "validated_intake":any(i.status==Status.VALIDATED and i.recording.speaker_id==speaker and i.recording.prompt_id==prompt.prompt_id for i in outcomes)} for speaker in speaker_ids}})
    coverage=[]
    for pattern in sorted({target.orthographic_pattern for _,target in all_targets}):
        rows=[t for t in targets if t["orthographic_pattern"]==pattern]
        coverage.append({"orthographic_pattern":pattern,"candidate_types":sorted({row["candidate_type"] for row in rows}),
                         "prompt_count":len({row["prompt_id"] for row in rows}),"target_count":len(rows),
                         "ready_target_count":sum(row["reference_profile_status"]=="READY_FOR_EXPERIMENT" for row in rows),
                         "insufficient_target_count":sum(row["reference_profile_status"]!="READY_FOR_EXPERIMENT" for row in rows)})
    failures=Counter(reason for item in outcomes for reason in item.reasons)
    failures.update(job.status for job in jobs if job.status not in {Status.REFERENCE_READY,Status.PLANNED,Status.REJECTED_INTAKE})
    report={"schema_version":"0.1","corpus_id":manifest.corpus_id,"prompt_pack_id":pack.prompt_pack_id,"prompt_pack_version":pack.prompt_pack_version,
            "prompt_pack_sha256":pack.sha256,"corpus_manifest_sha256":manifest.sha256,"tooling_ready":tooling_ready,"backend_resources_available":backend_available,
            "real_reference_data_ready":level=="REFERENCE_DATA_READY","dataset_status":level,
            "diagnosis_gate":"REFERENCE_DATA_GATE_SATISFIED_NO_DIAGNOSIS_IMPLEMENTED" if level=="REFERENCE_DATA_READY" else "BLOCKED_INSUFFICIENT_REFERENCE_DATA",
            "minimum_independent_speakers":policy.minimum_independent_speakers,"policy_role":"PROTOTYPE_ENGINEERING_POLICY_NOT_SCIENTIFIC_SAMPLE_SUFFICIENCY",
            "source_type_counts":dict(sorted(Counter(i.recording.source_type for i in outcomes).items())),
            "submitted_speaker_count":len(manifest.speakers),"submitted_session_count":len(manifest.sessions),"submitted_recording_count":len(outcomes),
            "validated_recording_count":sum(i.status==Status.VALIDATED for i in outcomes),
            "validated_speaker_count":len({i.recording.speaker_id for i in outcomes if i.status==Status.VALIDATED}),
            "eligible_real_reference_speaker_count":len({i.recording.speaker_id for i in real}),"eligible_real_reference_recording_count":len(real),
            "prompt_count":len(pack.prompts),"target_count":len(targets),"ready_target_count":ready,"insufficient_target_count":len(targets)-ready,
            "per_prompt":per_prompt,"per_target":targets,"coverage_matrix":{"speaker_ids":speaker_ids,"rows":matrix},"linguistic_coverage":coverage,
            "per_speaker_completion":[{"speaker_id":speaker,"validated_prompt_count":len({i.recording.prompt_id for i in outcomes if i.status==Status.VALIDATED and i.recording.speaker_id==speaker}),
                                       "eligible_prompt_count":len({i.recording.prompt_id for i in real if i.recording.speaker_id==speaker})} for speaker in speaker_ids],
            "failure_counts":dict(sorted(failures.items())),"intake_outcomes":[i.to_dict() for i in outcomes],"batch_outcomes":[j.to_dict() for j in jobs],
            "external_research_smoke":inspect_external_sets(manifest,policy),"reference_profiles":[p.to_dict() for p in profiles],
            "generated_reference_inputs":[reference_input_value(p) for p in profiles],
            "generated_input_provenance_role":"REPORT_EMBEDDED_MANIFEST_FRAGMENT_SHA256_OF_EVIDENCE_JSON_BYTES",
            "speaker_session_manifest_hashes":[{"path":path,"sha256":sha} for path,sha in manifest.metadata_sources],
            "warnings":["SELF_REPORTED_METADATA_NOT_INFERRED_FROM_AUDIO","EXACT_HASH_DUPLICATE_CHECK_IS_NOT_IDENTITY_PROOF",
                        "TEST_SYNTHETIC_EXTERNAL_SOURCES_EXCLUDED_FROM_CONTROLLED_READINESS","NO_LEARNER_DIAGNOSIS_OR_PRONUNCIATION_THRESHOLDS"]}
    return report,tuple(profiles)


def export_profiles(profiles,folder):
    from .pipeline import new_text
    from speech_xray.reference.manifest import load_manifest
    for profile in profiles:
        path=Path(folder)/profile.manifest.target.target_id
        manifest_path=path/"reference-set.json"
        profile_path=path/"reference-profile.json"
        value=reference_input_value(profile)
        payload=evidence_json(value)
        # Existing files must have the same bytes; never overwrite a different run.
        if manifest_path.exists():
            if manifest_path.read_text(encoding="utf-8")!=payload:
                raise ValueError("EXISTING_REFERENCE_MANIFEST_DIFFERS")
        else:
            new_text(manifest_path,payload)
        exported=build_reference_profile(load_manifest(manifest_path),profile.policy)
        if profile_path.exists():
            if profile_path.read_text(encoding="utf-8")!=exported.to_json():
                raise ValueError("EXISTING_REFERENCE_PROFILE_DIFFERS")
        else:
            new_text(profile_path,exported.to_json())
