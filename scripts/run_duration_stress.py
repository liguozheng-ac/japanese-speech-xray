"""Local-only controlled duration benchmark; execution is explicit."""
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services/speech-api/src'))
from speech_xray.stress.selection import select_bases
from speech_xray.stress.runner import run
from speech_xray.acoustics.models import evidence_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    selection = sub.add_parser('select')
    selection.add_argument('--accepted-build', required=True)
    selection.add_argument('--output', required=True)
    benchmark = sub.add_parser('run')
    benchmark.add_argument('--plan', required=True)
    benchmark.add_argument('--output', required=True)
    benchmark.add_argument('--execute', action='store_true')
    benchmark.add_argument('--controls-only', action='store_true')
    args = parser.parse_args()
    try:
        if args.operation == 'select':
            result = select_bases(args.accepted_build, args.output)
            print(evidence_json({'status': 'SELECTED', 'base_count': result['base_count'], 'case_count': result['expected_case_count']}))
        else:
            result = run(args.plan, args.output, args.execute, args.controls_only)
            print(evidence_json(result.get('gates', {'status': result.get('status')})))
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(evidence_json({'status': 'STRESS_EXECUTION_FAILED', 'reason': str(error)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
