"""Build a new prompt/target reference artifact, without extracting or diagnosing speech."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/speech-api/src"))
from speech_xray.reference.manifest import load_manifest
from speech_xray.reference.models import ProfileStatus, ReferencePolicy
from speech_xray.reference.profile_builder import build_reference_profile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--minimum-independent-speakers", type=int, default=ReferencePolicy().minimum_independent_speakers)
    args = parser.parse_args()
    source, output = args.manifest.resolve(), args.output.resolve()
    if not source.is_relative_to(ROOT) or not output.is_relative_to(ROOT):
        parser.error("Manifest/output must remain within this project")
    if output == source or output.exists():
        parser.error("Output must be a new file distinct from source artifacts")
    try:
        manifest = load_manifest(source)
        if any(output == Path(ref.path) for entry in manifest.entries for _, ref in entry.sources):
            parser.error("Output must differ from every source artifact")
        policy = ReferencePolicy(args.minimum_independent_speakers)
        profile = build_reference_profile(manifest, policy)
        payload = profile.to_json()
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            stream.write(payload)
    except (OSError, ValueError) as error:
        print(f"Cannot build reference profile: {error}", file=sys.stderr)
        return 1
    print(f"{profile.profile_status}: {len(profile.speakers)} speakers, "
          f"{sum(len(speaker.takes) for speaker in profile.speakers)} valid takes -> {output}")
    return 1 if profile.rejected else 0


if __name__ == "__main__":
    raise SystemExit(main())
