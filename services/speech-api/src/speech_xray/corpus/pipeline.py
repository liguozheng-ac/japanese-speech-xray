"""Small local batch runner, retaining each failure and immutable previous runs."""

from pathlib import Path
import os
import shutil
import subprocess

from speech_xray.alignment.textgrid_parser import parse_textgrid
from speech_xray.japanese.long_vowel_mapper import analyze_mora
from speech_xray.japanese.reading import SudachiReadingProvider
from speech_xray.acoustics.config import AcousticConfig
from speech_xray.acoustics.mora_input import load_mora_analysis
from speech_xray.acoustics.pipeline import extract_acoustic_evidence
from speech_xray.acoustics.models import evidence_json
from .batch_plan import digest,model_resources,object_hash,output_paths,plan_batch
from .integrity import assess_receipt,canonical_transcript
from .models import BatchOutcome,RecordingStatus as Status
from .validation import PROJECT_ROOT


def new_text(path,text):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf-8") as stream:
        stream.write(text)


def mfa_align(paths,recording):
    if any(not item["actual_sha256"] or item["actual_sha256"]!=item["expected_sha256"] for item in model_resources()):
        raise ValueError("PINNED_LOCAL_MFA_RESOURCES_REQUIRED_NO_DOWNLOAD")
    for variable in ("MFA_ROOT_DIR","USERPROFILE","TEMP","XDG_CACHE_HOME","PYTHONPYCACHEPREFIX"):
        value=os.environ.get(variable)
        if not value or not Path(value).resolve().is_relative_to(PROJECT_ROOT):
            raise ValueError("DOT_SOURCE_PROJECT_ENV_BEFORE_ALIGNMENT")
    folder=Path(paths["run_directory"])
    argv=[str(PROJECT_ROOT/".tools/Library/bin/micromamba.exe"),"--no-rc","run","-p",str(PROJECT_ROOT/".envs/mfa"),
          "mfa","align",str(folder/"input"),"japanese_mfa","japanese_mfa",str(folder/"aligned"),
          "--g2p_model_path","japanese_mfa","--temporary_directory",str(folder/"mfa-temp"),
          "--single_speaker","--num_jobs","1","--no_use_postgres","--clean"]
    with (folder/"alignment.log").open("x",encoding="utf-8") as log:
        process=subprocess.run(argv,cwd=PROJECT_ROOT,stdout=log,stderr=subprocess.STDOUT,check=False)
    if process.returncode!=0 or not Path(paths["textgrid"]).is_file():
        raise ValueError("MFA_ALIGNMENT_DID_NOT_PRODUCE_VALID_OUTPUT")


def run_batch(manifest,pack,outcomes,config,acoustic_config=AcousticConfig(),aligner=mfa_align):
    planned=plan_batch(manifest,pack,outcomes,config)
    results=[]
    prompts={p.prompt_id:p for p in pack.prompts}
    if config["acoustics"]!=acoustic_config.to_dict():
        raise ValueError("EXTRACTION_CONFIG_DIFFERS_FROM_PLAN")
    for job in planned:
        if job.status not in {Status.PLANNED,Status.REBUILD_REQUIRED}:
            results.append(job)
            continue
        intake=job.intake
        signature,paths=output_paths(manifest,pack,intake,config)
        failure=Status.ALIGNMENT_FAILED
        try:
            folder=Path(paths["run_directory"])
            folder.mkdir(parents=True,exist_ok=False)
            if digest(intake.recording.audio_path)!=intake.audio_sha256:
                raise ValueError("SOURCE_CHANGED_AFTER_INTAKE")
            Path(paths["prepared_audio"]).parent.mkdir(parents=True)
            shutil.copyfile(intake.recording.audio_path,paths["prepared_audio"])
            if digest(paths["prepared_audio"])!=intake.audio_sha256:
                raise ValueError("PREPARED_AUDIO_HASH_MISMATCH")
            new_text(paths["transcript"],canonical_transcript(prompts[intake.recording.prompt_id]))
            aligner(paths,intake.recording)
            alignment=parse_textgrid(Path(paths["textgrid"]))
            new_text(paths["alignment"],alignment.to_json())
            failure=Status.MORA_MAPPING_FAILED
            mora=analyze_mora(alignment,SudachiReadingProvider())
            new_text(paths["mora_analysis"],mora.to_json())
            failure=Status.ACOUSTIC_EXTRACTION_FAILED
            acoustic=extract_acoustic_evidence(intake.recording.audio_path,load_mora_analysis(paths["mora_analysis"]),acoustic_config)
            new_text(paths["acoustic_evidence"],acoustic.to_json())
            if acoustic.extraction_status in {"INVALID_AUDIO","F0_EXTRACTION_FAILED","ENERGY_EXTRACTION_FAILED","F0_CONFIG_UNSUPPORTED"}:
                raise ValueError("ACOUSTIC_BACKEND_UNAVAILABLE")
            failure=Status.REFERENCE_INTEGRITY_FAILED
            receipt={"schema_version":"0.1","recording_id":intake.recording.key,"session_id":intake.recording.session_id,
                     "source_type":intake.recording.source_type,"input_audio_sha256":intake.audio_sha256,
                     "prompt_pack_sha256":pack.sha256,"configuration_sha256":object_hash(config),"input_signature":signature,
                     "artifacts":{name:{"path":paths[name],"sha256":digest(paths[name])} for name in
                                  ("alignment","mora_analysis","acoustic_evidence","transcript")}}
            new_text(paths["receipt"],evidence_json(receipt))
            results.append(assess_receipt(manifest,pack,intake,config,Path(paths["receipt"]),paths,signature))
        except (OSError,ValueError,RuntimeError):
            # Logs contain opaque IDs and authored prompt text; source files stay untouched.
            result=BatchOutcome(intake,failure,"STAGE_FAILED_OR_INCOMPLETE_RUN_REQUIRES_REVIEW",tuple(sorted(paths.items())))
            results.append(result)
            failed_path=Path(paths["run_directory"])/"failure-report.json"
            if failed_path.parent.is_dir() and not failed_path.exists():
                new_text(failed_path,evidence_json(result.to_dict()))
    return tuple(results)
