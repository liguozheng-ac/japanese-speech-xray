"""Offline replay only; requires a previously frozen private evidence build."""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'services/speech-api/src'))
from speech_xray.jvs_reference.reconciliation import reconcile

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--previous-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    args = parser.parse_args()
    reconcile(args.source_root, args.previous_root, args.output_root)
