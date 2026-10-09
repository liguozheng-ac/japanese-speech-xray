"""Export a TextGrid to Speech X-Ray's 0.1 evidence schema."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/speech-api/src"))
from speech_xray.alignment.textgrid_parser import TextGridParseError, parse_textgrid


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("textgrid", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    if args.textgrid.resolve() == args.output.resolve():
        cli.error("Output must differ from the source TextGrid")
    try:
        result = parse_textgrid(args.textgrid)
        payload = result.to_json()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    except (OSError, TextGridParseError) as error:
        print(f"Cannot parse alignment: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
