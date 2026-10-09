"""Run with the locked project speech runtime and project-local MFA resources."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services/speech-api/src'))
from speech_xray.jvs_reference.cli import main
if __name__=='__main__':raise SystemExit(main())
