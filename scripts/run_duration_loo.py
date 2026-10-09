"""Run only a private duration native-reference self-consistency experiment."""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services/speech-api/src'))
from speech_xray.deviation.loo import run_experiment,run_target

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-root',type=Path,required=True)
    parser.add_argument('--output-root',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=5)
    parser.add_argument('--target-index',type=int)
    args=parser.parse_args()
    if args.target_index is not None:
        run_target(args.reference_root,args.output_root,args.target_index)
    else:
        result=run_experiment(args.reference_root,args.output_root,args.workers)
        print('Completed comparisons',result['comparison_count'],'self leakage',result['self_leakage_count'],flush=True)
