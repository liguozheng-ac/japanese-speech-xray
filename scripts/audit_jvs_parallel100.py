from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/speech-api/src"))
from speech_xray.external_jvs.cli import main
if __name__=="__main__":raise SystemExit(main())
