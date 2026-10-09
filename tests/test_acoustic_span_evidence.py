"""Exact association, quantization and timing ownership without acoustic diagnoses."""

from dataclasses import replace
from decimal import Decimal, localcontext
from fractions import Fraction
import json
import unittest

from acoustic_test_support import analysis
from speech_xray.acoustics.models import AcousticFrame, AcousticTrack, ExtractionStatus as Status, evidence_json
from speech_xray.acoustics.span_evidence import span_evidence, summarize
from speech_xray.acoustics.timing import center_in_span, quantize_interval, sample_time_ms


def authored_track():
    frames = []
    for index, center in enumerate((0, 10, 20, 30, 40)):
        voiced = index != 2
        frames.append(AcousticFrame(index, center - 10, center, center + 10,
                                    max(0, center - 10), center + 10, max(0, 10 - center), 0,
                                    Decimal(center - 10), Decimal(center), Decimal(center + 10),
                                    200.0 + index if voiced else None, voiced, 0.8 if voiced else 0.0,
                                    0.1 * (index + 1)))
    return AcousticTrack(1000, 100, tuple(frames), Status.OK, Status.OK)


class AcousticSpanTests(unittest.TestCase):
    def setUp(self):
        self.span = replace(analysis().long_vowel_spans[0], start_ms=Decimal(10), end_ms=Decimal(30))
        self.track = authored_track()

    def test_center_inclusion_is_half_open_and_deterministic(self):
        first = span_evidence(self.track, self.span, "a" * 64)
        second = span_evidence(self.track, self.span, "a" * 64)
        self.assertEqual(first, second)
        self.assertEqual(first.selected_frame_indices, (1, 2))
        self.assertEqual(first.frame_count, 2)
        self.assertEqual(first.voiced_frame_count, 1)
        self.assertEqual(first.voiced_frame_ratio, 0.5)
        self.assertEqual(first.raw_f0_hz.count, 1)
        self.assertEqual(first.raw_f0_hz.median, 201.0)
        self.assertEqual(first.rms.count, 2)
        self.assertEqual(first.sample_interval.sample_start, 10)
        self.assertEqual(first.sample_interval.sample_end, 30)
        self.assertEqual(first.selected_window_observed_sample_interval.sample_start, 0)
        self.assertEqual(first.selected_window_observed_sample_interval.sample_end, 30)

    def test_boundaries_and_one_span_identity_are_unchanged(self):
        evidence = span_evidence(self.track, self.span, "a" * 64)
        self.assertIs(evidence.original_span, self.span)
        self.assertEqual(evidence.to_dict()["alignment_start_ms"], Decimal(10))
        self.assertEqual(evidence.to_dict()["alignment_end_ms"], Decimal(30))
        self.assertEqual(evidence.to_dict()["mora_span"], 2)
        self.assertNotIn("mora_intervals", evidence.to_dict())
        self.assertNotIn("midpoint", evidence.to_dict())

    def test_out_of_range_and_reversed_spans_are_not_clipped(self):
        for start, end in (("-1", "10"), ("90", "101")):
            evidence = span_evidence(self.track, replace(self.span, start_ms=Decimal(start), end_ms=Decimal(end)), "a" * 64)
            self.assertEqual(evidence.extraction_status, Status.SPAN_OUT_OF_AUDIO_RANGE)
            self.assertIsNone(evidence.sample_interval)
            self.assertEqual(evidence.selected_frame_indices, ())
        evidence = span_evidence(self.track, replace(self.span, start_ms=Decimal(30), end_ms=Decimal(10)), "a" * 64)
        self.assertEqual(evidence.extraction_status, Status.INVALID_SPAN)

    def test_very_short_and_zero_spans_have_no_frames(self):
        for start, end in (("10.1", "10.2"), ("10", "10")):
            evidence = span_evidence(self.track, replace(self.span, start_ms=Decimal(start), end_ms=Decimal(end)), "a" * 64)
            self.assertEqual(evidence.extraction_status, Status.NO_FRAMES)
            self.assertIsNone(evidence.voiced_frame_ratio)
            self.assertIsNone(evidence.raw_f0_hz.median)
        self.assertEqual(quantize_interval(Decimal("10.1"), Decimal("10.1"), 1000), (10, 10))

    def test_quantization_uses_floor_and_ceil_not_float_rounding(self):
        self.assertEqual(quantize_interval(Decimal("860.00000000000000000000000001"),
                                           Decimal("1010.00000000000000000000000002"), 24000), (20640, 24241))
        self.assertEqual(quantize_interval(Decimal("860"), Decimal("1010"), 24000), (20640, 24240))

    def test_rational_selection_does_not_depend_on_display_time_rounding(self):
        with localcontext() as context:
            context.prec = 6
            self.assertFalse(center_in_span(1, 24000, Decimal("0.0416"),
                                            Decimal("0.04166666666666666666666666666666666")))
            self.assertTrue(center_in_span(1, 24000, Decimal("0.0416"), Decimal("0.0417")))
            self.assertEqual(sample_time_ms(1, 24000), Decimal("0.04166666666666666666666666666666667"))

    def test_decimal_source_boundaries_survive_json(self):
        start = Decimal("10.000000000000000000000000000001")
        end = Decimal("30.000000000000000000000000000002")
        with localcontext() as context:
            context.prec = 6
            evidence = span_evidence(self.track, replace(self.span, start_ms=start, end_ms=end), "a" * 64)
            text = evidence_json(evidence.to_dict())
        payload = json.loads(text, parse_float=Decimal, parse_int=Decimal)
        self.assertEqual(payload["alignment_start_ms"], start)
        self.assertEqual(payload["alignment_end_ms"], end)
        self.assertEqual(payload["alignment_duration_ms"], Decimal("20.000000000000000000000000000001"))
        self.assertNotIn("NaN", text)
        self.assertNotIn("Infinity", text)

    def test_summary_is_descriptive_and_empty_summary_is_null(self):
        summary = summarize((1.0, 2.0, 3.0, 4.0))
        self.assertEqual((summary.median, summary.minimum, summary.maximum, summary.iqr), (2.5, 1.0, 4.0, 1.5))
        self.assertEqual(summarize(()).count, 0)
        self.assertIsNone(summarize(()).median)
        with self.assertRaises(ValueError):
            summarize((float("inf"),))

    def test_duration_changes_never_create_diagnosis_fields(self):
        forbidden = {"score", "correct", "incorrect", "confidence", "severity", "diagnosis",
                     "native_reference", "semitone_deviation"}
        for end in ("10", "10.1", "30", "100", "150"):
            payload = span_evidence(self.track, replace(self.span, end_ms=Decimal(end)), "a" * 64).to_dict()
            self.assertFalse(forbidden & set(payload))
            self.assertTrue(forbidden.isdisjoint(payload["raw_f0_hz"]))


if __name__ == "__main__":
    unittest.main()
