"""Inspect real local alignment artifacts; report observations without diagnosis."""

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/speech-api/src"))
from speech_xray.alignment.textgrid_parser import parse_textgrid


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("textgrid", type=Path)
    cli.add_argument("wav", type=Path)
    cli.add_argument("exported_json", type=Path)
    cli.add_argument("inspection_json", type=Path)
    args = cli.parse_args()
    for name, path in vars(args).items():
        resolved = path.resolve()
        if not resolved.is_relative_to(ROOT):
            raise ValueError("All artifact paths must stay within the project")
        setattr(args, name, resolved)
    result = parse_textgrid(args.textgrid)
    exported = json.loads(args.exported_json.read_text(encoding="utf-8"),
                          parse_float=Decimal, parse_int=Decimal)
    if exported != result.to_dict():
        raise ValueError("Exported JSON differs from parsed source boundaries")
    words = [word for word in result.words if word.label]
    phones = [phone for phone in result.phones if phone.label and phone.label not in {"sil", "sp", "spn"}]
    if not words or not phones:
        raise ValueError("Alignment must contain nonempty word and phone evidence")
    info = sf.info(args.wav)
    audio_ms = Decimal(info.frames) * 1000 / Decimal(info.samplerate)
    if abs(result.duration_ms - audio_ms) > Decimal("0.001"):
        raise ValueError("TextGrid duration does not match the actual audio")
    long_labels = {"oː", "iː", "eː", "aː", "ɯː", "ɨː"}
    # Numeric values below are stringified for an auxiliary observation report;
    # the primary schema export retains exact JSON numeric tokens.
    report = {
        "textgrid": args.textgrid.relative_to(ROOT).as_posix(),
        "textgrid_sha256": hashlib.sha256(args.textgrid.read_bytes()).hexdigest(),
        "json": args.exported_json.relative_to(ROOT).as_posix(),
        "word_interval_count": len(result.words),
        "nonempty_word_interval_count": len(words),
        "phone_interval_count": len(result.phones),
        "nonempty_speech_phone_count": len(phones),
        "empty_phone_intervals": sum(not phone.label for phone in result.phones),
        "explicit_silence_phone_intervals": sum(phone.label in {"sil", "sp"} for phone in result.phones),
        "unknown_phone_intervals": sum(phone.label == "spn" for phone in result.phones),
        "duration_ms": str(result.duration_ms),
        "phone_labels": sorted({phone.label for phone in result.phones}),
        "long_vowel_observations": [
            {key: str(value) if isinstance(value, Decimal) else value
             for key, value in phone.to_dict().items()}
            for phone in result.phones if phone.label in long_labels
        ],
        "json_matches_source_decimal_boundaries": True,
        "acoustic_correctness_verified": False,
    }
    args.inspection_json.parent.mkdir(parents=True, exist_ok=True)
    args.inspection_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
