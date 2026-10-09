"""Development-only commands: explicit new reports, private corpus outputs."""

import argparse
from pathlib import Path
import sys

from speech_xray.acoustics.models import evidence_json
from speech_xray.reference.models import ReferencePolicy
from .batch_plan import batch_plan_report,object_hash,pipeline_configuration,plan_batch
from .intake import load_corpus_manifest,validate_corpus
from .pipeline import new_text,run_batch
from .prompt_manifest import load_prompt_pack,recording_sheet,validate_prompt_pack
from .readiness import build_readiness,export_profiles
from .validation import PRIVATE_ROOT,PROJECT_ROOT

DEFAULT_PACK=PROJECT_ROOT/"data/prompts/reference-long-vowel-v1.json"


def new_output(path,private=False):
    path=Path(path).resolve()
    boundary=PRIVATE_ROOT.resolve() if private else PROJECT_ROOT
    if not path.is_relative_to(boundary) or path.exists():
        raise ValueError("OUTPUT_MUST_BE_NEW_AND_WITHIN_ALLOWED_ROOT")
    return path


def prompt_main():
    parser=argparse.ArgumentParser(description="Validate authored readings/candidates and generate an unprimed recording sheet")
    parser.add_argument("--prompt-pack",type=Path,default=DEFAULT_PACK)
    parser.add_argument("--qa-output",required=True,type=Path)
    parser.add_argument("--sheet-output",type=Path)
    args=parser.parse_args()
    try:
        qa_path=new_output(args.qa_output)
        sheet_path=new_output(args.sheet_output) if args.sheet_output else None
        if sheet_path==qa_path or qa_path==args.prompt_pack.resolve():
            raise ValueError("OUTPUT_COLLIDES_WITH_INPUT_OR_REPORT")
        pack=load_prompt_pack(args.prompt_pack)
        qa=validate_prompt_pack(pack)
        new_text(qa_path,evidence_json(qa))
        if sheet_path and qa["status"]=="PASS":
            new_text(sheet_path,recording_sheet(pack))
        print(f"{qa['status']}: {len(pack.prompts)} prompts, {qa['target_count']} authoring targets")
        return 0 if qa["status"]=="PASS" else 1
    except (OSError,ValueError,TypeError,KeyError):
        print("PROMPT_AUTHORING_OR_OUTPUT_VALIDATION_FAILED",file=sys.stderr)
        return 1


def corpus_main(mode):
    parser=argparse.ArgumentParser(description="Validate/plan/process private reference inputs without pronunciation diagnosis")
    parser.add_argument("--corpus-manifest",required=True,type=Path)
    parser.add_argument("--prompt-pack",default=DEFAULT_PACK,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--minimum-independent-speakers",default=5,type=int)
    parser.add_argument("--run-label",default="default")
    parser.add_argument("--dry-run",action="store_true",help="Write only the explicitly requested report; no derived evidence writes")
    if mode=="run":
        parser.add_argument("--execute",action="store_true",help="Run local MFA/analysis on validated inputs, retaining every outcome")
    args=parser.parse_args()
    if mode=="run" and args.execute and args.dry_run:
        parser.error("Choose --execute or --dry-run")
    try:
        output=new_output(args.output,private=True)
        pack=load_prompt_pack(args.prompt_pack)
        qa=validate_prompt_pack(pack)
        manifest=load_corpus_manifest(args.corpus_manifest)
        if (manifest.prompt_pack_id,manifest.prompt_pack_version,manifest.prompt_pack_sha256)!=(
                pack.prompt_pack_id,pack.prompt_pack_version,pack.sha256):
            raise ValueError("CORPUS_PROMPT_PACK_BINDING_MISMATCH")
        if output==Path(manifest.source) or any(output==Path(r.audio_path) or output==Path(r.evidence_receipt or manifest.source) for r in manifest.recordings):
            raise ValueError("OUTPUT_COLLIDES_WITH_SOURCE")
        policy=ReferencePolicy(args.minimum_independent_speakers)
        outcomes=validate_corpus(manifest,pack)
        config=pipeline_configuration(run_label=args.run_label)
        if mode=="validate":
            value={"schema_version":"0.1","corpus_id":manifest.corpus_id,"prompt_pack_sha256":pack.sha256,
                   "corpus_manifest_sha256":manifest.sha256,"prompt_authoring_status":qa["status"],
                   "submitted_recording_count":len(outcomes),"validated_recording_count":sum(i.status=="VALIDATED" for i in outcomes),
                   "outcomes":[i.to_dict() for i in outcomes]}
        else:
            execute=mode=="run" and args.execute
            if execute and qa["status"]!="PASS":
                raise ValueError("AUTHORING_VALIDATION_REQUIRED_BEFORE_EXECUTION")
            jobs=run_batch(manifest,pack,outcomes,config) if execute else plan_batch(manifest,pack,outcomes,config)
            if mode=="plan":
                value=batch_plan_report(manifest,pack,jobs,config)
            else:
                value,profiles=build_readiness(manifest,pack,outcomes,jobs,qa,policy)
                if execute and profiles:
                    signature=object_hash({"manifest":manifest.sha256,"pack":pack.sha256,"config":object_hash(config),"policy":policy.minimum_independent_speakers})
                    export_profiles(profiles,Path(manifest.corpus_root)/"derived/reference"/signature[:32])
                value["execution_requested"]=bool(execute)
        new_text(output,evidence_json(value))
        invalid=qa["status"]!="PASS" or any(i.status=="REJECTED_INTAKE" for i in outcomes)
        if mode in {"run","readiness"}:
            invalid=invalid or any(j.status not in {"REFERENCE_READY","PLANNED"} for j in jobs)
        print(f"{'REVIEW_REQUIRED' if invalid else 'OK'}: {manifest.corpus_id}, {len(outcomes)} recordings; report written")
        return 1 if invalid else 0
    except (OSError,ValueError,TypeError,KeyError):
        print("CORPUS_SCHEMA_PATH_OR_OUTPUT_VALIDATION_FAILED",file=sys.stderr)
        return 1
