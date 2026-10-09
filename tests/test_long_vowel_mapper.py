"""Structured self-authored alignments test mapping, abstention and exact timing."""

from decimal import Decimal, localcontext
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/speech-api/src"))
from speech_xray.alignment.models import AlignmentResult, PhoneInterval, WordInterval
from speech_xray.japanese.long_vowel_mapper import analyze_mora
from speech_xray.japanese.models import MappingBasis, ReadingResult, UnresolvedReason as Reason
from speech_xray.japanese.vowel import is_long_vowel_phone, phone_vowel_class


class KnownReading:
    def __init__(self, reading):
        self.reading = reading

    def reading_for(self, surface):
        return ReadingResult(surface, self.reading, source="SELF_AUTHORED_TEST_READING")


def alignment(reading, labels):
    return AlignmentResult("self-authored.json", Decimal(0), Decimal(len(labels)),
                           (WordInterval(reading, Decimal(0), Decimal(len(labels))),),
                           tuple(PhoneInterval(label, Decimal(index), Decimal(index + 1))
                                 for index, label in enumerate(labels)))


class LongVowelMapperTests(unittest.TestCase):
    def run_case(self, reading, labels):
        return analyze_mora(alignment(reading, labels), KnownReading(reading))

    def reasons(self, result):
        return {item.reason for item in result.unresolved_items}

    def test_explicit_prolonged_mark(self):
        result = self.run_case("コー", ["k", "oː"])
        span, = result.long_vowel_spans
        self.assertEqual(span.mora_indices, (0, 1))
        self.assertEqual(span.mora_span, 2)
        self.assertEqual(span.phone_index, 1)
        self.assertEqual(span.mapping_basis, MappingBasis.PROLONGED_MARK)
        self.assertEqual(result.unresolved_items, ())
        self.assertEqual([mora.long_vowel_span_ids for mora in result.morae], [(span.id,), (span.id,)])

    def test_o_plus_u_and_no_invented_boundary(self):
        result = self.run_case("トウ", ["t", "oː"])
        span, = result.long_vowel_spans
        self.assertEqual(span.mapping_basis, MappingBasis.KANA_SEQUENCE)
        self.assertEqual([result.morae[index].text for index in span.mora_indices], ["ト", "ウ"])
        self.assertEqual((span.start_ms, span.end_ms), (Decimal(1), Decimal(2)))
        self.assertTrue(all(not {"start_ms", "end_ms", "duration_ms"} & set(mora.to_dict())
                            for mora in result.morae))

    def test_e_plus_i_is_candidate_with_e_long_phone(self):
        result = self.run_case("ケイ", ["k", "eː"])
        self.assertEqual(result.long_vowel_spans[0].vowel_class, "E")
        self.assertEqual(result.long_vowel_spans[0].mora_indices, (0, 1))
        split = self.run_case("ケイ", ["k", "e", "i"])
        self.assertEqual(split.long_vowel_spans, ())
        self.assertIn(Reason.NO_MATCHING_LONG_PHONE, self.reasons(split))

    def test_vowel_class_mismatch(self):
        result = self.run_case("トウ", ["t", "iː"])
        self.assertEqual(result.long_vowel_spans, ())
        self.assertIn(Reason.VOWEL_CLASS_MISMATCH, self.reasons(result))
        self.assertEqual(result.long_vowel_candidates[0].to_dict()["status"], "UNRESOLVED")

    def test_no_long_phone_does_not_merge_short_phones(self):
        result = self.run_case("トウ", ["t", "o", "ɨ"])
        self.assertEqual(result.long_vowel_spans, ())
        self.assertIn(Reason.NO_MATCHING_LONG_PHONE, self.reasons(result))

    def test_multiple_long_vowels_keep_order(self):
        result = self.run_case("コーヒー", ["k", "oː", "h", "iː"])
        self.assertEqual([span.mora_indices for span in result.long_vowel_spans], [(0, 1), (2, 3)])
        self.assertEqual([span.phone_index for span in result.long_vowel_spans], [1, 3])
        repeated = self.run_case("コーコー", ["k", "oː", "k", "oː"])
        self.assertEqual(len(repeated.long_vowel_spans), 2)
        self.assertFalse(repeated.unresolved_items)

    def test_repeated_local_choices_without_full_coverage_are_ambiguous(self):
        result = self.run_case("コーコー", ["oː"])
        self.assertEqual(result.long_vowel_spans, ())
        self.assertIn(Reason.AMBIGUOUS_PHONE_MAPPING, self.reasons(result))

    def test_all_word_vowels_anchor_candidate_position(self):
        result = self.run_case("カトウ", ["k", "a", "t", "oː"])
        self.assertEqual(result.long_vowel_spans[0].mora_indices, (1, 2))
        bad_prefix = self.run_case("カトウ", ["k", "i", "t", "oː"])
        self.assertEqual(bad_prefix.long_vowel_spans, ())
        self.assertIn(Reason.VOWEL_SEQUENCE_MISMATCH, self.reasons(bad_prefix))

    def test_special_mora_are_not_long_candidates(self):
        result = self.run_case("ガッコウ", ["ɡ", "a", "kː", "oː"])
        self.assertEqual(result.long_vowel_spans[0].mora_indices, (2, 3))
        self.assertFalse(is_long_vowel_phone("kː"))
        nasal = self.run_case("コンウ", ["k", "oː"])
        self.assertEqual(nasal.long_vowel_spans, ())
        self.assertIn(Reason.NO_LONG_VOWEL_CANDIDATE, self.reasons(nasal))

    def test_no_reading_and_unsupported_kana(self):
        source = alignment("unknown", ["oː"])
        result = analyze_mora(source, KnownReading(None))
        self.assertEqual(result.morae, ())
        self.assertIn(Reason.NO_READING, self.reasons(result))
        result = self.run_case("コA", ["oː"])
        self.assertEqual(result.morae, ())
        self.assertIn(Reason.UNSUPPORTED_KANA, self.reasons(result))
        result = self.run_case("ー", ["oː"])
        self.assertIn(Reason.INVALID_PROLONGED_MARK, self.reasons(result))

    def test_unknown_phone_and_internal_silence_block_mapping(self):
        for label in ("spn", "uː", "not-an-MFA-phone"):
            result = self.run_case("コー", [label, "oː"])
            self.assertFalse(result.long_vowel_spans)
            self.assertIn(Reason.UNSUPPORTED_PHONE, self.reasons(result))
        result = self.run_case("コー", ["k", "sil", "oː"])
        self.assertFalse(result.long_vowel_spans)
        self.assertIn(Reason.INTERNAL_SILENCE, self.reasons(result))

    def test_crossing_word_boundary_blocks_mapping(self):
        source = AlignmentResult("crossing.json", Decimal(0), Decimal(4),
            (WordInterval("コー", Decimal(0), Decimal(2)), WordInterval("コー", Decimal(2), Decimal(4))),
            (PhoneInterval("oː", Decimal(1), Decimal(3)),))
        result = analyze_mora(source, KnownReading("コー"))
        self.assertEqual(result.long_vowel_spans, ())
        self.assertIn(Reason.WORD_PHONE_BOUNDARY_MISMATCH, self.reasons(result))
        self.assertEqual({item.word_index for item in result.unresolved_items}, {0, 1})

    def test_zero_length_shared_boundary_is_ambiguous(self):
        source = AlignmentResult("zero.json", Decimal(0), Decimal(4),
            (WordInterval("コー", Decimal(0), Decimal(2)), WordInterval("コー", Decimal(2), Decimal(4))),
            (PhoneInterval("oː", Decimal(2), Decimal(2)),))
        result = analyze_mora(source, KnownReading("コー"))
        self.assertFalse(result.long_vowel_spans)
        self.assertIn(Reason.AMBIGUOUS_PHONE_MAPPING, self.reasons(result))

    def test_speech_outside_any_word_is_retained_as_unresolved(self):
        source = AlignmentResult("outside.json", Decimal(0), Decimal(4),
            (WordInterval("コー", Decimal(1), Decimal(2)),),
            (PhoneInterval("oː", Decimal(3), Decimal(4)),))
        result = analyze_mora(source, KnownReading("コー"))
        self.assertTrue(any(item.word_index is None and item.phone_indices == (0,)
                            for item in result.unresolved_items))

    def test_nonempty_word_with_no_phone_evidence_is_unresolved(self):
        source = AlignmentResult("missing.json", Decimal(0), Decimal(1),
                                 (WordInterval("カ", Decimal(0), Decimal(1)),), ())
        result = analyze_mora(source, KnownReading("カ"))
        self.assertEqual(result.words[0].mapping_status, "UNRESOLVED")
        self.assertIn(Reason.NO_PHONE_EVIDENCE, self.reasons(result))

    def test_no_candidates_is_not_a_successful_full_phone_mapping(self):
        result = self.run_case("カナ", ["k", "a", "n", "a"])
        self.assertEqual(result.words[0].mapping_status, "NO_CANDIDATES")
        self.assertEqual(result.long_vowel_candidates, ())
        self.assertEqual(result.long_vowel_spans, ())

    def test_one_supported_span_can_coexist_with_an_unmapped_candidate(self):
        result = self.run_case("コーヒー", ["k", "oː", "h", "i", "i"])
        self.assertEqual(len(result.long_vowel_spans), 1)
        self.assertEqual(result.long_vowel_spans[0].mora_indices, (0, 1))
        self.assertEqual(result.words[0].mapping_status, "UNRESOLVED")
        self.assertEqual([candidate.to_dict()["status"] for candidate in result.long_vowel_candidates],
                         ["MAPPED", "UNRESOLVED"])
        self.assertIn(Reason.NO_MATCHING_LONG_PHONE, self.reasons(result))

    def test_decimal_precision_and_duration_independence(self):
        start = Decimal("860.00000000000000000000000000001")
        end = Decimal("1010.00000000000000000000000000002")
        source = AlignmentResult("precision.json", Decimal(0), end,
            (WordInterval("トウ", start, end),), (PhoneInterval("oː", start, end),))
        with localcontext() as context:
            context.prec = 6
            result = analyze_mora(source, KnownReading("トウ"))
            payload = json.loads(result.to_json(), parse_float=Decimal, parse_int=Decimal)
        span = payload["long_vowel_spans"][0]
        self.assertEqual(span["start_ms"], start)
        self.assertEqual(span["end_ms"], end)
        self.assertEqual(span["duration_ms"], Decimal("150.00000000000000000000000000001"))
        for duration in ("0", "1", "149", "150", "9999"):
            source = AlignmentResult("any-duration.json", Decimal(0), Decimal(duration),
                (WordInterval("コー", Decimal(0), Decimal(duration)),),
                (PhoneInterval("oː", Decimal(0), Decimal(duration)),))
            self.assertEqual(len(analyze_mora(source, KnownReading("コー")).long_vowel_spans), 1)
        forbidden = {"score", "correct", "incorrect", "confidence", "severity", "diagnosis"}
        self.assertFalse(forbidden & set(payload))
        self.assertFalse(any(forbidden & set(item) for key in ("words", "morae", "long_vowel_spans")
                             for item in payload[key]))

    def test_vowel_adapter_inventory(self):
        for label, vowel in (("aː", "A"), ("iː", "I"), ("eː", "E"), ("oː", "O"),
                              ("ɨː", "U"), ("ɯː", "U")):
            self.assertTrue(is_long_vowel_phone(label))
            self.assertEqual(phone_vowel_class(label), vowel)
        for label, vowel in (("ɨ", "U"), ("ɯ", "U"), ("ɨ̥", "U"), ("ɯ̥", "U"), ("i̥", "I")):
            self.assertFalse(is_long_vowel_phone(label))
            self.assertEqual(phone_vowel_class(label), vowel)
        for label in ("kː", "ɴː", "uː", "g"):
            self.assertFalse(is_long_vowel_phone(label))
            self.assertIsNone(phone_vowel_class(label))


if __name__ == "__main__":
    unittest.main()
