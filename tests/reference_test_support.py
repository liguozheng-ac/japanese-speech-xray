"""Authored mathematical observations with silent WAVs; never human/TTS speech."""

from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import wave
import struct

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/speech-api/src"))
from speech_xray.alignment.models import AlignmentResult, PhoneInterval, WordInterval
from speech_xray.japanese.long_vowel_mapper import analyze_mora
from speech_xray.japanese.models import ReadingResult
from speech_xray.acoustics.config import AcousticConfig
from speech_xray.acoustics.models import AcousticEvidenceResult, AcousticFrame, AcousticTrack, AudioMetadata, ExtractionStatus, evidence_json
from speech_xray.acoustics.span_evidence import span_evidence
from speech_xray.acoustics.timing import sample_time_ms
from speech_xray.reference.numeric import decimal_ratio
from fractions import Fraction

TEXT = "コー" * 10  # Self-authored 20-mora mathematical utterance.
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()


class AuthoredReading:
    def reading_for(self, surface):
        return ReadingResult(surface, surface, source="SELF_AUTHORED_STRUCTURED_FIXTURE")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"), parse_int=Decimal, parse_float=Decimal)


def write_json(path, value):
    path.write_text(evidence_json(value), encoding="utf-8")


def bundle(directory, speaker, take, raw="150", core="4000", start="100", scale="1"):
    directory = directory / f"{speaker}-{take}"
    directory.mkdir(parents=True)
    raw, core, start, scale = map(Decimal, (raw, core, start, scale))
    raw, core, start = (decimal_ratio(Fraction(value) * Fraction(scale)) for value in (raw, core, start))
    end = decimal_ratio(Fraction(start) + Fraction(core))
    size = int(end) + 101
    audio = directory / "source.ref"
    # A valid sample domain supports the abstract corpus aggregation contract
    # under real-WAV decoding checks. The silent signal and timing remain
    # authored mathematical fixtures, not acquired reference recordings.
    with wave.open(str(audio), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(1000)
        stream.writeframes(b"\0\0" * size)
    # Keep independent authored takes byte-distinct without adding a sample.
    note = f"AUTHORED_SILENT_FIXTURE:{speaker}:{take}".encode("utf-8")
    wav_bytes = audio.read_bytes() + b"AUTH" + struct.pack("<I", len(note)) + note + (b"\0" if len(note) % 2 else b"")
    audio.write_bytes(wav_bytes[:4] + struct.pack("<I", len(wav_bytes) - 8) + wav_bytes[8:])
    transcript = directory / "authored.txt"
    transcript.write_text(TEXT, encoding="utf-8")
    phones = [PhoneInterval("", Decimal(0), start)]
    boundaries = [start, decimal_ratio(Fraction(start) + Fraction(raw))]
    for index in range(1, 10):
        boundaries.append(end if index == 9 else decimal_ratio(Fraction(start) + Fraction(raw)
                          + (Fraction(core) - Fraction(raw)) * index / 9))
    for left, right in zip(boundaries, boundaries[1:]):
        phones.append(PhoneInterval("oː", left, right))
    phones.append(PhoneInterval("", end, Decimal(size)))
    alignment = AlignmentResult("source.TextGrid", Decimal(0), Decimal(size),
                 (WordInterval("", Decimal(0), start), WordInterval(TEXT, start, end),
                  WordInterval("", end, Decimal(size))), tuple(phones))
    aligned_path = directory / "alignment.json"
    aligned_path.write_text(alignment.to_json(), encoding="utf-8")
    mora = analyze_mora(alignment, AuthoredReading())
    mora_path = directory / "mora.json"
    mora_path.write_text(mora.to_json(), encoding="utf-8")
    span = mora.long_vowel_spans[0]
    frames = []
    for index in range(1 + size // 100):
        center = index * 100
        frames.append(AcousticFrame(index, center - 100, center, center + 100,
                       max(0, center - 100), min(size, center + 100), max(0, 100 - center),
                       max(0, center + 100 - size), sample_time_ms(center - 100, 1000),
                       sample_time_ms(center, 1000), sample_time_ms(center + 100, 1000), 220.0, True, 0.9, 0.1))
    track = AcousticTrack(1000, size, tuple(frames), ExtractionStatus.OK, ExtractionStatus.OK)
    metadata = AudioMetadata(str(audio), digest(audio), 1000, 1, size, Decimal(size), "WAV",
                             "PCM_16", "IDENTITY_MONO_FLOAT64", 0.0, 0.0)
    acoustic = AcousticEvidenceResult(str(audio), str(mora_path), digest(mora_path), alignment.source,
                 metadata, AcousticConfig(frame_length=200, hop_length=100, fmax_hz=400),
                 (("fixture", "STRUCTURED_NOT_MEASURED_SPEECH"),), track,
                 tuple(span_evidence(track, item, digest(audio)) for item in mora.long_vowel_spans), ExtractionStatus.OK)
    acoustic_path = directory / "acoustic.json"
    acoustic_path.write_text(acoustic.to_json(), encoding="utf-8")
    paths = {"audio": audio, "alignment": aligned_path, "mora_analysis": mora_path,
             "acoustic_evidence": acoustic_path, "transcript": transcript}
    entry = {"prompt_id": "authored-20-mora", "target_id": "authored-20-mora-lv-01",
             "speaker_id": speaker, "take_id": take, "utterance_id": f"{speaker}-{take}", "span_id": span.id,
             "sources": {key: {"path": str(path), "sha256": digest(path)} for key, path in paths.items()}}
    return entry


def make_manifest(directory, specifications=None):
    if specifications is None:
        specifications = [(f"speaker-{index}", "take-1", str(120 + index * 15), str(1600 + index * 200)) for index in range(5)]
    entries = [bundle(directory, *spec) for spec in specifications]
    value = {"schema_version": "0.1", "reference_set_id": "self-authored-reference-math",
             "prompt_id": "authored-20-mora", "transcript_sha256": hashlib.sha256(TEXT.encode()).hexdigest(),
             "target": {"target_id": "authored-20-mora-lv-01", "word_index": 0, "word_mora_indices": [0, 1],
                        "phone_label": "oː", "vowel_class": "O", "mora_span": 2, "mapping_basis": "PROLONGED_MARK"},
             "dataset": {"name": "Self-authored structured mathematical observations", "source": "repository tests",
                         "local_only": False, "usage_restrictions": "Self-authored test data; not human reference speech",
                         "material_kind": "STRUCTURED_REFERENCE_FIXTURE"},
             "creation_metadata": {"label": "deterministic-mathematical-test"}, "entries": entries}
    path = directory / "reference-set.json"
    write_json(path, value)
    return path


def change_source(manifest_path, source_name, mutate, entry_index=0):
    manifest = read(manifest_path)
    entry = manifest["entries"][entry_index]
    source = Path(entry["sources"][source_name]["path"])
    value = read(source)
    mutate(value)
    write_json(source, value)
    entry["sources"][source_name]["sha256"] = digest(source)
    write_json(manifest_path, manifest)
