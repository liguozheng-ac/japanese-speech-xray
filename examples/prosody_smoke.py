"""Real pYIN extraction on supplied WAV or an explicitly non-speech test tone."""
from argparse import ArgumentParser
from io import BytesIO
from pathlib import Path
import json
import sys
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services/speech-api/src'))
from speech_xray.product.config import Settings
from speech_xray.prosody.extract import extract

def engineering_wav():
    rate = 16000
    t = np.arange(rate * 2) / rate
    signal = .2 * np.sin(2 * np.pi * 220 * t)
    signal[(t < .3) | (t > 1.7)] = 0
    buffer = BytesIO()
    sf.write(buffer, signal, rate, format='WAV', subtype='PCM_16')
    return buffer.getvalue()

if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--audio', type=Path)
    parser.add_argument('--save-json', type=Path)
    parser.add_argument('--generate-wav', type=Path)
    args = parser.parse_args()
    raw = args.audio.read_bytes() if args.audio else engineering_wav()
    if args.generate_wav:
        if args.audio: parser.error('--generate-wav is only for the non-speech test tone')
        args.generate_wav.write_bytes(raw)
    result = extract(raw, Settings())
    if args.save_json:
        args.save_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(input_kind='USER_SUPPLIED_WAV' if args.audio else 'ENGINEERING_TONE_NOT_HUMAN_SPEECH',
                        status=result['status'], reason=result['reason'],
                        frame_count=len(result['frames']), voiced_frames=sum(f['voiced'] for f in result['frames']),
                        reference_included=False, extraction_ms=result['extraction_ms']), ensure_ascii=False))
