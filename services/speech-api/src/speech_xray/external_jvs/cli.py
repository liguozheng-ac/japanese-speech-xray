"""Private reports only; corpus absent is explicit, not fabricated feasibility."""

import argparse
from pathlib import Path
import sys

from speech_xray.acoustics.models import evidence_json
from speech_xray.corpus.cli import new_output
from speech_xray.corpus.pipeline import new_text
from .inventory import inventory
from .discovery import discover,recommend,review_recommendation
from .smoke import choose_smoke,run_smoke


def main(smoke=False):
    parser=argparse.ArgumentParser(description="Audit local external JVS; preserve controlled readiness and private outputs")
    parser.add_argument("--corpus-root",required=True,type=Path)
    parser.add_argument("--layout",choices=("official","mfa-demo"),default="official")
    parser.add_argument("--output",required=True,type=Path)
    if smoke:
        parser.add_argument("--derived-root",type=Path)
        parser.add_argument("--execute",action="store_true")
        parser.add_argument("--prompt-limit",type=int,default=3)
        parser.add_argument("--speaker-limit",type=int,default=3)
        parser.add_argument("--run-label",default="default")
    args=parser.parse_args()
    try:
        output=new_output(args.output,private=True)
        observed=inventory(args.corpus_root,args.layout)
        linguistic=discover(observed)
        selection=recommend(linguistic)
        if smoke:
            records=choose_smoke(observed,linguistic,args.prompt_limit,args.speaker_limit)
            if args.execute:
                if not args.derived_root:raise ValueError("PRIVATE_DERIVED_ROOT_REQUIRED")
                value=run_smoke(observed,linguistic,records,args.derived_root,run_label=args.run_label)
                value["reviewed_recommendation"]=review_recommendation(selection,value,linguistic)
            else:value={"source_type":observed["source_type"],"scope":observed["scope"],"dry_run":True,"selected_recordings":list(records),"utterance_count":len(records)}
        else:value={"inventory":observed,"discovery":linguistic,"recommendation":selection}
        new_text(output,evidence_json(value))
        print(f"REPORT_WRITTEN: {observed['scope']}; speakers={observed['observed']['speaker_count']}; parallel WAVs={observed['observed']['parallel100_wav_count']}; lexical targets={linguistic['supported_target_count']}")
        return 1 if smoke and args.execute and any(r["status"]!="COMPATIBILITY_OBSERVED" for r in value["outcomes"]) else 0
    except (OSError,ValueError,TypeError,KeyError,IndexError):
        print("JVS_SCHEMA_PATH_OR_PIPELINE_REVIEW_REQUIRED",file=sys.stderr);return 1
