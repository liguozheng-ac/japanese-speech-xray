"""Development CLI and schema safety with public mathematical signals."""

from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from acoustic_test_support import ROOT, tone, write_wav, analysis
from speech_xray.acoustics.models import ExtractionStatus as Status
from speech_xray.acoustics.mora_input import load_mora_analysis
from speech_xray.acoustics.pipeline import extract_acoustic_evidence


class AcousticCliTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".tools/tmp").mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=ROOT / ".tools/tmp")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.wav = write_wav(self.path / "tone.wav", tone())
        self.analysis_path = self.path / "mora.json"
        self.analysis_path.write_text(analysis().to_json(), encoding="utf-8")

    def cli(self, output, wav=None):
        return subprocess.run([sys.executable, str(ROOT / "scripts/extract_acoustic_evidence.py"),
                               "--audio", str(wav or self.wav), "--mora-analysis", str(self.analysis_path),
                               "--output", str(output)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")

    def test_cli_preserves_inputs_and_serializes_full_track(self):
        inputs = [hashlib.sha256(path.read_bytes()).hexdigest() for path in (self.wav, self.analysis_path)]
        output = self.path / "evidence.json"
        process = self.cli(output)
        self.assertEqual(process.returncode, 0, process.stderr)
        value = json.loads(output.read_text(encoding="utf-8"), parse_float=Decimal, parse_int=Decimal,
                           parse_constant=lambda constant: self.fail(constant))
        self.assertEqual(value["representation"], "ACOUSTIC_EVIDENCE")
        self.assertGreater(len(value["track"]["frames"]), 0)
        span, = value["span_evidence"]
        self.assertEqual((span["alignment_start_ms"], span["alignment_end_ms"]), (100, 300))
        self.assertEqual(span["mora_span"], 2)
        self.assertEqual(inputs, [hashlib.sha256(path.read_bytes()).hexdigest() for path in (self.wav, self.analysis_path)])

    def test_existing_outputs_and_inputs_are_never_overwritten(self):
        for output in (self.wav, self.analysis_path):
            before = output.read_bytes()
            process = self.cli(output)
            self.assertNotEqual(process.returncode, 0)
            self.assertEqual(output.read_bytes(), before)
        output = self.path / "existing.json"
        output.write_text("keep existing evidence", encoding="utf-8")
        process = self.cli(output)
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(output.read_text(encoding="utf-8"), "keep existing evidence")

    def test_invalid_audio_has_structured_output_and_nonzero_cli_exit(self):
        output = self.path / "invalid.json"
        process = self.cli(output, self.path / "missing.wav")
        self.assertNotEqual(process.returncode, 0)
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["extraction_status"], "INVALID_AUDIO")
        self.assertIsNone(payload["track"])
        self.assertEqual(payload["span_evidence"][0]["extraction_status"], "INVALID_AUDIO")

    def test_mora_schema_and_conflicting_references_are_rejected(self):
        original = analysis().to_json()
        variants = [original.replace('"schema_version": "0.1"', '"schema_version": "9"'),
                    original.replace('"schema_version":', '"schema_version": "duplicate", "schema_version":'),
                    original.replace('"phone_index": 0', '"phone_index": 9'),
                    original.replace('"duration_ms": 200', '"duration_ms": 201'),
                    original.replace('"start_ms": 100', '"start_ms": NaN')]
        for variant in variants:
            self.analysis_path.write_text(variant, encoding="utf-8")
            with self.assertRaises(ValueError):
                load_mora_analysis(self.analysis_path)
        output = self.path / "no-output.json"
        self.assertNotEqual(self.cli(output).returncode, 0)
        self.assertFalse(output.exists())

    def test_same_environment_config_input_has_deterministic_json(self):
        source = load_mora_analysis(self.analysis_path)
        first = extract_acoustic_evidence(self.wav, source)
        second = extract_acoustic_evidence(self.wav, source)
        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual(first.mora_analysis_sha256, hashlib.sha256(self.analysis_path.read_bytes()).hexdigest())

    def test_out_of_audio_span_reports_partial_and_cli_failure(self):
        self.analysis_path.write_text(analysis(start="450", end="550").to_json(), encoding="utf-8")
        output = self.path / "outside.json"
        process = self.cli(output)
        self.assertNotEqual(process.returncode, 0)
        value = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(value["extraction_status"], "PARTIAL_EVIDENCE")
        self.assertEqual(value["span_evidence"][0]["extraction_status"], "SPAN_OUT_OF_AUDIO_RANGE")
        self.assertIsNone(value["span_evidence"][0]["sample_interval"])


if __name__ == "__main__":
    unittest.main()
