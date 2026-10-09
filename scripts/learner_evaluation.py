"""Local-only learner intake, blind packages, discovery and pipeline planning."""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services/speech-api/src'))
from speech_xray.evaluation.learner_manifest import load_learner_manifest,validate_import
from speech_xray.evaluation.annotation import blind_package
from speech_xray.evaluation.discovery import discover_candidates
from speech_xray.evaluation.pipeline import analyse_learner,observation
from speech_xray.evaluation.serialization import save,serialize


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('import','blind','discover','analyse'))
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--observation-id')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--analysis-root',type=Path)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args(argv)
    try:
        dataset=load_learner_manifest(args.manifest)
        if args.execute and args.operation!='analyse':raise ValueError('EXECUTE_ONLY_VALID_FOR_ANALYSIS')
        if args.operation=='import':
            result={'schema_version':'0.1','dataset_identity':dataset.identity,'source_type':dataset.data['source_type'],
                    'dataset_role':'LEARNER','import_outcomes':list(validate_import(dataset))}
        else:
            if not args.observation_id:raise ValueError('OBSERVATION_ID_REQUIRED')
            if args.operation=='blind':result=blind_package(dataset,args.observation_id)
            elif args.operation=='discover':result=discover_candidates(observation(dataset,args.observation_id)['transcript'])
            else:
                if args.analysis_root is None:raise ValueError('PRIVATE_ANALYSIS_ROOT_REQUIRED')
                result=analyse_learner(dataset,args.observation_id,args.analysis_root,execute=args.execute)
        save(args.output,result)
        print(serialize({'status':'SAVED_PRIVATE','output':str(args.output)}))
        return 0
    except (OSError,ValueError,KeyError) as error:
        print(serialize({'status':'INVALID_EVALUATION_INPUT','reason':str(error)}));return 1


if __name__=='__main__':raise SystemExit(main())
