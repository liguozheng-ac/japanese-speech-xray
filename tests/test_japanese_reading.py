"""Public self-authored reading cases, using the unchanged installed Sudachi API."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/speech-api/src"))
from speech_xray.japanese.models import UnresolvedReason
from speech_xray.japanese.reading import SudachiReadingProvider, normalize_katakana


class JapaneseReadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider = SudachiReadingProvider()

    def test_normalization_preserves_unknown_characters(self):
        self.assertEqual(normalize_katakana("きょう ｺｰﾋｰ う\u3099 ABC"), "キョウ コーヒー ヴ ABC")
        self.assertEqual(normalize_katakana("ティー"), "ティー")

    def test_dictionary_word_readings(self):
        for surface, reading in (("学校", "ガッコウ"), ("コーヒー", "コーヒー"), ("ティー", "ティー")):
            with self.subTest(surface=surface):
                result = self.provider.reading_for(surface)
                self.assertTrue(result.resolved)
                self.assertEqual(result.surface, surface)
                self.assertEqual(result.reading, reading)
                self.assertTrue(all(not piece.is_oov for piece in result.pieces))

    def test_hiragana_reading(self):
        result = self.provider.reading_for("きょう")
        self.assertTrue(result.resolved)
        self.assertEqual(result.reading, "キョウ")

    def test_oov_numerals_and_symbols_are_not_guessed(self):
        for surface in ("abcXYZ", "123", "🧪", "。"):
            with self.subTest(surface=surface):
                result = self.provider.reading_for(surface)
                self.assertFalse(result.resolved)
                self.assertIsNone(result.reading)
                self.assertEqual(result.reason, UnresolvedReason.NO_READING)

    def test_empty_reading(self):
        for surface in ("", " "):
            result = self.provider.reading_for(surface)
            self.assertFalse(result.resolved)
            self.assertEqual(result.reason, UnresolvedReason.NO_READING)


if __name__ == "__main__":
    unittest.main()
