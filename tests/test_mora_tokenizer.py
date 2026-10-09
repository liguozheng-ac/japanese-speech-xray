"""Self-authored kana strings only; no corpus-derived fixtures."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/speech-api/src"))
from speech_xray.japanese.models import MappingBasis, MoraKind, UnresolvedReason, VowelClass
from speech_xray.japanese.mora_tokenizer import tokenize_mora
from speech_xray.japanese.long_vowel_mapper import long_vowel_candidates


class MoraTokenizerTests(unittest.TestCase):
    def check(self, reading, expected):
        result = tokenize_mora(reading)
        self.assertIsNone(result.issue)
        self.assertEqual([mora.text for mora in result.morae], expected)
        return result.morae

    def test_basic_kana_and_indices(self):
        morae = self.check("カタカナ", ["カ", "タ", "カ", "ナ"])
        self.assertEqual([mora.index for mora in morae], [0, 1, 2, 3])
        self.assertTrue(all(mora.kind == MoraKind.NORMAL for mora in morae))
        shifted = tokenize_mora("カナ", word_index=3, start_index=8).morae
        self.assertEqual([(mora.index, mora.word_index, mora.word_mora_index) for mora in shifted],
                         [(8, 3, 0), (9, 3, 1)])

    def test_yoon(self):
        self.check("キョウ", ["キョ", "ウ"])
        for text, vowel in (("シャ", VowelClass.A), ("リュ", VowelClass.U), ("ギョ", VowelClass.O)):
            morae = self.check(text, [text])
            self.assertEqual(morae[0].vowel_class, vowel)

    def test_loanword_rule_table(self):
        for text, vowel in (("ティ", "I"), ("ファ", "A"), ("フィ", "I"), ("フェ", "E"),
                            ("フォ", "O"), ("ウィ", "I"), ("ウェ", "E"), ("ウォ", "O"),
                            ("トゥ", "U"), ("ヴェ", "E"), ("シェ", "E"), ("チェ", "E")):
            with self.subTest(text=text):
                morae = self.check(text, [text])
                self.assertEqual(morae[0].vowel_class, vowel)
        morae = self.check("ティー", ["ティ", "ー"])
        self.assertEqual(morae[1].kind, MoraKind.LONG_VOWEL_EXTENSION)
        self.assertEqual(morae[1].vowel_class, VowelClass.I)

    def test_moraic_nasal(self):
        morae = self.check("ホン", ["ホ", "ン"])
        self.assertEqual(morae[1].kind, MoraKind.MORAIC_NASAL)
        self.assertIsNone(morae[1].vowel_class)

    def test_geminate(self):
        morae = self.check("ガッコウ", ["ガ", "ッ", "コ", "ウ"])
        self.assertEqual(morae[1].kind, MoraKind.GEMINATE)
        self.assertIsNone(morae[1].vowel_class)

    def test_coffee_four_morae_and_no_times(self):
        morae = self.check("コーヒー", ["コ", "ー", "ヒ", "ー"])
        self.assertEqual([mora.kind for mora in morae],
                         [MoraKind.NORMAL, MoraKind.LONG_VOWEL_EXTENSION] * 2)
        self.assertEqual([mora.vowel_class for mora in morae], ["O", "O", "I", "I"])
        self.assertTrue(all("start_ms" not in mora.to_dict() and "end_ms" not in mora.to_dict()
                            for mora in morae))

    def test_hiragana_and_halfwidth(self):
        self.check("きょう", ["キョ", "ウ"])
        self.check("がっこう", ["ガ", "ッ", "コ", "ウ"])
        self.check("ｺｰﾋｰ", ["コ", "ー", "ヒ", "ー"])

    def test_invalid_prolonged_mark(self):
        for reading in ("ー", "ンー", "ッー"):
            with self.subTest(reading=reading):
                result = tokenize_mora(reading)
                self.assertEqual(result.issue.reason, UnresolvedReason.INVALID_PROLONGED_MARK)
                self.assertFalse(any(mora.kind == MoraKind.LONG_VOWEL_EXTENSION for mora in result.morae))

    def test_unsupported_kana_and_empty_reading(self):
        for reading in ("ァ", "キァ", "カャ", "ティョ", "カ。", "カA", "ヽ"):
            self.assertEqual(tokenize_mora(reading).issue.reason, UnresolvedReason.UNSUPPORTED_KANA)
        self.assertEqual(tokenize_mora("").issue.reason, UnresolvedReason.NO_READING)

    def test_all_conservative_candidates(self):
        for reading, vowel in (("カア", "A"), ("キイ", "I"), ("クウ", "U"), ("ケエ", "E"),
                               ("ケイ", "E"), ("コオ", "O"), ("トウ", "O")):
            with self.subTest(reading=reading):
                candidate, = long_vowel_candidates(tokenize_mora(reading).morae)
                self.assertEqual(candidate.mora_indices, (0, 1))
                self.assertEqual(candidate.vowel_class, vowel)
                self.assertEqual(candidate.mapping_basis, MappingBasis.KANA_SEQUENCE)
                self.assertIsNone(candidate.span_id)
        candidate, = long_vowel_candidates(tokenize_mora("コー").morae)
        self.assertEqual(candidate.mapping_basis, MappingBasis.PROLONGED_MARK)

    def test_candidate_barriers_and_other_sequences(self):
        for reading in ("コンウ", "コッウ", "カイ", "コエ"):
            self.assertEqual(long_vowel_candidates(tokenize_mora(reading).morae), ())
        # Repeated marks are linguistic positions; this layer does not guess 3-mora acoustics.
        self.assertEqual(len(self.check("コーー", ["コ", "ー", "ー"])), 3)


if __name__ == "__main__":
    unittest.main()
