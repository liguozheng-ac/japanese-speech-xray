"""Stable input schema and development CLI checks with public authored data."""

from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/speech-api/src"))
from speech_xray.alignment.models import AlignmentResult, PhoneInterval, WordInterval
from speech_xray.japanese.alignment_input import load_alignment


def fixture():
    return AlignmentResult("public-coffee.json", Decimal(0), Decimal(4),
        (WordInterval("コーヒー", Decimal(0), Decimal(4)),),
        tuple(PhoneInterval(label, Decimal(index), Decimal(index + 1))
              for index, label in enumerate(("k", "oː", "h", "iː"))))


class MoraCliTests(unittest.TestCase):
    def setUp(self):
        local_tmp = ROOT / ".tools/tmp"
        local_tmp.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=local_tmp)
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.source = self.path / "alignment.json"
        self.source.write_text(fixture().to_json(), encoding="utf-8")

    def run_cli(self, source, output):
        return subprocess.run([sys.executable, str(ROOT / "scripts/analyze_mora.py"),
                               str(source), str(output)], cwd=ROOT, capture_output=True,
                              text=True, encoding="utf-8")

    def test_alignment_json_round_trip(self):
        self.assertEqual(load_alignment(self.source), fixture())
        grid = load_alignment(ROOT / "tests/fixtures/alignment.TextGrid")
        self.assertEqual(grid.phones[3].label, "oː")
        self.assertEqual(grid.phones[-1].end_ms, Decimal("500.000000000000000000000000001"))

    def test_invalid_json_and_boundaries_rejected(self):
        variants = [fixture().to_json().replace('"schema_version": "0.1"', '"schema_version": "9"'),
                    fixture().to_json().replace('"source":', '"source": "duplicate", "source":'),
                    fixture().to_json().replace('"end_ms": 4', '"end_ms": NaN', 1),
                    fixture().to_json().replace('"duration_ms": 4', '"duration_ms": 99', 1),
                    fixture().to_json().replace('"start_ms": 0', '"start_ms": true', 1),
                    fixture().to_json().replace('"duration_ms": 1', '"duration_ms": 99', 1)]
        for variant in variants:
            with self.subTest(variant=variant[:90]):
                self.source.write_text(variant, encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_alignment(self.source)
        bad = fixture().to_json().replace('"start_ms": 1', '"start_ms": 0', 1)
        self.source.write_text(bad, encoding="utf-8")
        with self.assertRaises(ValueError):
            load_alignment(self.source)

    def test_cli_json_exports_mora_without_overwriting_alignment(self):
        original_bytes = self.source.read_bytes()
        output = self.path / "mora.json"
        process = self.run_cli(self.source, output)
        self.assertEqual(process.returncode, 0, process.stderr)
        payload = json.loads(output.read_text(encoding="utf-8"), parse_float=Decimal)
        self.assertEqual(payload["schema_version"], "0.1")
        self.assertEqual(len(payload["morae"]), 4)
        self.assertEqual(len(payload["long_vowel_spans"]), 2)
        self.assertFalse(payload["unresolved_items"])
        self.assertEqual(self.source.read_bytes(), original_bytes)

    def test_cli_accepts_original_textgrid_parser(self):
        output = self.path / "grid-mora.json"
        process = self.run_cli(ROOT / "tests/fixtures/alignment.TextGrid", output)
        self.assertEqual(process.returncode, 0, process.stderr)
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["alignment_source"], "alignment.TextGrid")
        # This authored fixture has two long vowel nuclei and omits consonants;
        # mapping covers the vowel skeleton, not a full consonant alignment.
        self.assertEqual(len(payload["long_vowel_spans"]), 2)
        self.assertFalse(payload["unresolved_items"])

    def test_cli_preserves_input_and_existing_output(self):
        before = self.source.read_bytes()
        process = self.run_cli(self.source, self.source)
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(self.source.read_bytes(), before)
        output = self.path / "already-there.json"
        output.write_text("preserve this evidence", encoding="utf-8")
        process = self.run_cli(self.source, output)
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(output.read_text(encoding="utf-8"), "preserve this evidence")

    def test_cli_malformed_input_creates_no_output(self):
        self.source.write_text('{"bad": true}', encoding="utf-8")
        output = self.path / "should-not-exist.json"
        process = self.run_cli(self.source, output)
        self.assertNotEqual(process.returncode, 0)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
