"""Content-addressed local jobs; hashes/configuration determine reuse, not filenames."""

import hashlib
from importlib.metadata import version
import json
from pathlib import Path

from speech_xray.acoustics.config import AcousticConfig
from .models import BatchOutcome, RecordingStatus as Status
from .validation import PROJECT_ROOT


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def object_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def model_resources():
    resources=json.loads((PROJECT_ROOT/"docs/task002-resources.json").read_text(encoding="utf-8"))
    return [{"path":item["path"],"expected_sha256":item["sha256"].lower(),
             "actual_sha256":digest(PROJECT_ROOT/item["path"]) if (PROJECT_ROOT/item["path"]).is_file() else None}
            for item in resources]


def pipeline_configuration(acoustic_config=AcousticConfig(), run_label="default"):
    from .validation import identifier
    code={path.relative_to(PROJECT_ROOT).as_posix():digest(path) for folder in ("alignment","japanese","acoustics","reference","corpus")
          for path in sorted((PROJECT_ROOT/"services/speech-api/src/speech_xray"/folder).glob("*.py"))}
    return {"version":"0.1", "run_label":identifier(run_label), "alignment":{"backend":"MFA_CPU_CLI", "dictionary":"japanese_mfa",
                "acoustic_model":"japanese_mfa", "g2p_model":"japanese_mfa", "single_speaker":True, "num_jobs":1, "use_postgres":False},
            "acoustics":acoustic_config.to_dict(), "reading":{"adapter":"SUDACHI_CORE_SPLIT_B","sudachipy":version("SudachiPy"),
                "sudachidict-core":version("SudachiDict-core")},
            "environment_locks":{name:digest(PROJECT_ROOT/"docs"/name) for name in
                ("task002-conda-win-64.explicit.txt","task004-speech-api-win-64.explicit.txt")},
            "model_resource_metadata_sha256":digest(PROJECT_ROOT/"docs/task002-resources.json"),
            "model_resources":model_resources(), "analysis_code_sha256":code}


def output_paths(manifest,pack,intake,config):
    recording=intake.recording
    signature=object_hash({"audio":intake.audio_sha256,"audio_path":recording.audio_path,"pack":pack.sha256,
                           "recording":recording.key,"session":recording.session_id,"source_type":recording.source_type,
                           "configuration":object_hash(config),"corpus_manifest":manifest.sha256,
                           "speaker_session_manifests":manifest.metadata_sources})
    folder=Path(manifest.corpus_root)/"derived/runs"/signature[:32]/recording.key
    stem=recording.key
    paths={"run_directory":str(folder), "prepared_audio":str(folder/"input"/(stem+".wav")),
           "transcript":str(folder/"input"/(stem+".lab")), "textgrid":str(folder/"aligned"/(stem+".TextGrid")),
           "alignment":str(folder/"alignment.json"), "mora_analysis":str(folder/"mora-analysis.json"),
           "acoustic_evidence":str(folder/"acoustic-evidence.json"), "receipt":str(folder/"evidence-receipt.json")}
    return signature,paths


def plan_batch(manifest,pack,outcomes,config):
    from .integrity import assess_receipt
    jobs=[]
    for intake in outcomes:
        signature,paths=output_paths(manifest,pack,intake,config)
        if intake.status!=Status.VALIDATED:
            job=BatchOutcome(intake,Status.REJECTED_INTAKE,"INTAKE_REJECTED",tuple(sorted(paths.items())))
        else:
            receipt=Path(intake.recording.evidence_receipt or paths["receipt"])
            if receipt.exists() or intake.recording.evidence_receipt:
                job=assess_receipt(manifest,pack,intake,config,receipt,paths,signature)
            else:
                job=BatchOutcome(intake,Status.PLANNED,"NO_VERIFIED_DERIVED_EVIDENCE",tuple(sorted(paths.items())))
        jobs.append(job)
    return tuple(jobs)


def batch_plan_report(manifest,pack,jobs,config):
    return {"schema_version":"0.1","corpus_id":manifest.corpus_id,"prompt_pack_id":pack.prompt_pack_id,
            "prompt_pack_version":pack.prompt_pack_version,"prompt_pack_sha256":pack.sha256,"corpus_manifest_sha256":manifest.sha256,
            "dry_run":True,"configuration":config,"configuration_sha256":object_hash(config),
            "jobs":[{**job.to_dict(),"prompt_targets":[t.target_id for p in pack.prompts if p.prompt_id==job.intake.recording.prompt_id for t in p.targets],
                     "stages":["PREPARE_UNCHANGED_WAV_AND_KNOWN_PROMPT_LAB","MFA_CPU_ALIGNMENT","TASK002_PARSE",
                               "TASK003_MORA","TASK004_ACOUSTICS","TASK005_REFERENCE_INTEGRITY_AND_PROFILES"]} for job in jobs]}
