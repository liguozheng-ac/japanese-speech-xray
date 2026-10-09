"""Export linguistic mora positions and unsplit acoustic long-vowel mappings."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/speech-api/src"))
from speech_xray.japanese.alignment_input import load_alignment
from speech_xray.japanese.long_vowel_mapper import analyze_mora
from speech_xray.japanese.reading import SudachiReadingProvider


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("alignment", type=Path, help="TASK-002 schema 0.1 JSON or text TextGrid")
    cli.add_argument("output", type=Path, help="New project-local JSON; existing files are never overwritten")
    args = cli.parse_args()
    source, output = args.alignment.resolve(), args.output.resolve()
    if source == output:
        cli.error("Output must differ from input alignment")
    if not source.is_relative_to(ROOT) or not output.is_relative_to(ROOT):
        cli.error("Development input/output paths must stay within this project")
    if output.exists():
        cli.error("Output already exists; choose a new path to preserve existing evidence")
    try:
        result = analyze_mora(load_alignment(source), SudachiReadingProvider())
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            stream.write(result.to_json())
    except (OSError, ValueError) as error:
        print(f"Cannot analyze mora representation: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {len(result.morae)} morae, {len(result.long_vowel_spans)} long-vowel spans, "
          f"{len(result.unresolved_items)} unresolved items to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
