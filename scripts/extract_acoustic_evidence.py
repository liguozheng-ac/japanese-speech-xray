"""Write a new local acoustic evidence artifact; never overwrite prior evidence."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/speech-api/src"))
from speech_xray.acoustics.config import AcousticConfig
from speech_xray.acoustics.models import ExtractionStatus
from speech_xray.acoustics.mora_input import load_mora_analysis
from speech_xray.acoustics.pipeline import extract_acoustic_evidence


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--audio", required=True, type=Path)
    cli.add_argument("--mora-analysis", required=True, type=Path)
    cli.add_argument("--output", required=True, type=Path)
    defaults = AcousticConfig()
    cli.add_argument("--frame-length", type=int, default=defaults.frame_length)
    cli.add_argument("--hop-length", type=int, default=defaults.hop_length)
    cli.add_argument("--fmin-hz", type=float, default=defaults.fmin_hz)
    cli.add_argument("--fmax-hz", type=float, default=defaults.fmax_hz)
    cli.add_argument("--center", action=argparse.BooleanOptionalAction, default=defaults.center)
    args = cli.parse_args()
    audio, analysis, output = args.audio.resolve(), args.mora_analysis.resolve(), args.output.resolve()
    if any(not path.is_relative_to(ROOT) for path in (audio, analysis, output)):
        cli.error("Development input/output paths must remain within this project")
    if output in (audio, analysis) or output.exists():
        cli.error("Output must be a new file distinct from all input evidence")
    try:
        config = AcousticConfig(frame_length=args.frame_length, hop_length=args.hop_length,
                                fmin_hz=args.fmin_hz, fmax_hz=args.fmax_hz, center=args.center)
        result = extract_acoustic_evidence(audio, load_mora_analysis(analysis), config)
        payload = result.to_json()
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            stream.write(payload)
    except (OSError, ValueError) as error:
        print(f"Cannot extract acoustic evidence: {error}", file=sys.stderr)
        return 1
    print(f"{result.extraction_status}: {len(result.track.frames) if result.track else 0} frames, "
          f"{len(result.spans)} span records -> {output}")
    fatal = {ExtractionStatus.INVALID_AUDIO, ExtractionStatus.F0_EXTRACTION_FAILED,
             ExtractionStatus.ENERGY_EXTRACTION_FAILED, ExtractionStatus.F0_CONFIG_UNSUPPORTED}
    invalid_spans = {ExtractionStatus.INVALID_SPAN, ExtractionStatus.SPAN_OUT_OF_AUDIO_RANGE}
    return 1 if (result.extraction_status in fatal
                 or any(span.extraction_status in invalid_spans for span in result.spans)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
