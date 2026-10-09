from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"services/speech-api/src"))
from speech_xray.corpus.cli import corpus_main
if __name__=="__main__":
    raise SystemExit(corpus_main("validate"))
