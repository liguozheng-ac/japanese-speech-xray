"""Text-only parser fixtures: these are not recordings or pronunciation evidence."""

from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/speech-api/src"))
from speech_xray.alignment.textgrid_parser import TextGridParseError, parse_textgrid

FIXTURE = ROOT / "tests/fixtures/alignment.TextGrid"


class ParserTests(unittest.TestCase):
    def parse_text(self, text):
        # TEMP is redirected to project-local .tools/tmp by task002-env.ps1.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.TextGrid"
            path.write_text(text, encoding="utf-8")
            return parse_textgrid(path)

    def test_valid_unicode_and_intervals(self):
        result = parse_textgrid(FIXTURE)
        self.assertEqual(result.source, "alignment.TextGrid")
        self.assertEqual(len(result.words), 2)
        self.assertEqual(result.words[1].label, "コーヒー")
        self.assertEqual([p.label for p in result.phones], ["", "sil", "", "oː", "iː"])
        self.assertEqual(result.phones[2].duration_ms, Decimal(0))
        self.assertEqual(result.phones[3].duration_ms, Decimal(200))

    def test_decimal_precision_survives_json(self):
        result = parse_textgrid(FIXTURE)
        payload = json.loads(result.to_json(), parse_float=Decimal, parse_int=Decimal)
        self.assertEqual(payload["schema_version"], "0.1")
        self.assertEqual(payload["duration_ms"], Decimal("500.000000000000000000000000001"))
        self.assertEqual(payload["phones"][-1]["duration_ms"], Decimal("200.000000000000000000000000001"))
        self.assertNotIn("diagnosis", payload)

    def test_short_form_nonzero_origin_and_escaped_string(self):
        result = self.parse_text('''File type = "ooTextFile short"
"TextGrid"
1
1.25
<exists>
2
"IntervalTier"
"speaker - words"
1
1.25
1
1
1.25
"a ""quote"""
"IntervalTier"
"speaker - phones"
1
1.25
1
1
1.25
"oː"
''')
        self.assertEqual(result.start_ms, Decimal(1000))
        self.assertEqual(result.duration_ms, Decimal(250))
        self.assertEqual(result.words[0].label, 'a "quote"')

    def test_malformed_inputs(self):
        original = FIXTURE.read_text(encoding="utf-8")
        variants = [
            "not a TextGrid", original[:-30],
            original.replace('text = "iː"', 'text = "unterminated'),
            original.replace('xmax = 0.05', 'xmax = -0.05'),
            original.replace('xmin = 0.3', 'xmin = 0.2'),
            original.replace('name = "phones"', 'name = "other"'),
            original.replace('name = "phones"', 'name = "words"'),
            original.replace('intervals: size = 5', 'intervals: size = 5.5'),
            original.replace('xmax = 0.05', 'xmax = NaN'),
            original + '\n123',
        ]
        for text in variants:
            with self.subTest(text=text[-60:]):
                with self.assertRaises(TextGridParseError):
                    self.parse_text(text)

    def test_utf8_bom(self):
        self.assertEqual(len(self.parse_text('\ufeff' + FIXTURE.read_text(encoding="utf-8")).phones), 5)

    def test_extra_point_tier(self):
        text = FIXTURE.read_text(encoding="utf-8").replace('size = 2\nitem', 'size = 3\nitem', 1)
        text += '''
item [3]:
class = "TextTier"
name = "notes"
xmin = 0
xmax = 0.5
points: size = 1
points [1]:
number = 0.2
mark = "manual note"
'''
        self.assertEqual(len(self.parse_text(text).phones), 5)

    def test_cli_export(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            process = subprocess.run([sys.executable, str(ROOT / 'scripts/parse_alignment.py'),
                                      str(FIXTURE), str(output)], capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads(output.read_text(encoding='utf-8'), parse_float=Decimal)
            self.assertEqual(result['phones'][3]['label'], 'oː')


if __name__ == "__main__":
    unittest.main()
