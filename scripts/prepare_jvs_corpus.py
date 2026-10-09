"""Validate a local JVS WAV/LAB pair and copy it unchanged into a minimal corpus."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]


def local_path(value: str) -> Path:
    path = Path(value).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("All data paths must stay within the project")
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("source_wav")
    cli.add_argument("corpus")
    cli.add_argument("provenance")
    args = cli.parse_args()
    source, corpus, output = map(local_path, (args.source_wav, args.corpus, args.provenance))
    transcript_file = source.with_suffix(".lab")
    transcript = transcript_file.read_text(encoding="utf-8-sig")
    if not transcript.strip():
        raise ValueError("Matching upstream transcript is empty")
    info = sf.info(source)
    samples, sample_rate = sf.read(source, dtype="float64", always_2d=True)
    if info.format != "WAV" or info.frames <= 0 or info.channels <= 0:
        raise ValueError("Expected a nonempty readable WAV")
    if not np.isfinite(samples).all() or not np.any(samples):
        raise ValueError("Non-finite or all-zero audio")
    if sample_rate != info.samplerate or samples.shape != (info.frames, info.channels):
        raise ValueError("Decoded audio does not match its header")
    corpus.mkdir(parents=True, exist_ok=True)
    other_wavs = [path for path in corpus.glob("*.wav") if path.name != source.name]
    if other_wavs:
        raise ValueError("Destination must contain only the selected utterance")
    for path in (source, transcript_file):
        destination = corpus / path.name
        shutil.copyfile(path, destination)
        if sha256(path) != sha256(destination):
            raise ValueError("Copied corpus differs from upstream")
    result = {
        "upstream_repository": "https://github.com/MontrealCorpusTools/japanese-jvs-demo",
        "corpus_name": "Japanese JVS demo",
        "tag": "v1.0.0",
        "tag_commit": "727c7cf2d52fd4dd154624a62a32ffd1db9b214e",
        "download_date": "2026-10-01",
        "speaker_id": source.parent.name,
        "source_wav": source.relative_to(ROOT).as_posix(),
        "source_transcript": transcript_file.relative_to(ROOT).as_posix(),
        "basename": source.stem,
        "transcript": transcript,
        "audio_sha256": sha256(source),
        "transcript_sha256": sha256(transcript_file),
        "frames": info.frames,
        "duration_seconds": info.duration,
        "sample_rate": info.samplerate,
        "channels": info.channels,
        "format": info.format,
        "encoding": info.subtype,
        "decoded_peak_abs": float(np.max(np.abs(samples))),
        "corpus_path": corpus.relative_to(ROOT).as_posix(),
        "conversion": None,
        "usage": "LOCAL TEST DATA ONLY; JVS audio terms; no redistribution",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
