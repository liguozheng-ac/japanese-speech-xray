from decimal import Decimal, localcontext
from pathlib import Path
import tempfile
import unittest

from reference_test_support import ROOT, make_manifest
from speech_xray.alignment.models import AlignmentResult, WordInterval
from speech_xray.japanese.models import LongVowelSpan, MappingBasis, VowelClass
from speech_xray.reference.manifest import load_manifest
from speech_xray.reference.models import ReferencePolicy
from speech_xray.reference.normalization import normalize_duration
from speech_xray.reference.profile_builder import build_reference_profile
from speech_xray.reference.robust_stats import summarize
from speech_xray.reference.speech_rate import measure_utterance_rate

D = Decimal


class ReferenceStatisticsTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".tools/tmp").mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=ROOT / ".tools/tmp")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)

    def profile(self, specs=None, minimum=5):
        return build_reference_profile(load_manifest(make_manifest(self.path, specs)), ReferencePolicy(minimum))

    def test_known_rate_20_mora_4_seconds(self):
        alignment = AlignmentResult("authored", D(0), D(4500),
                     (WordInterval("", D(0), D(100)), WordInterval("word", D(100), D(4100)),
                      WordInterval("", D(4100), D(4500))), ())
        rate = measure_utterance_rate(alignment, 20)
        self.assertEqual((rate.core_speech_start_ms, rate.core_speech_end_ms,
                          rate.core_speech_duration_ms, rate.utterance_mora_rate_per_second,
                          rate.mean_mora_period_ms), (100, 4100, 4000, 5, 200))

    def test_internal_pause_included_outer_silence_excluded(self):
        alignment = AlignmentResult("authored", D(0), D(5000),
                    (WordInterval("", D(0), D(500)), WordInterval("a", D(500), D(1000)),
                     WordInterval("", D(1000), D(3000)), WordInterval("b", D(3000), D(4500)),
                     WordInterval("", D(4500), D(5000))), ())
        self.assertEqual(measure_utterance_rate(alignment, 20).core_speech_duration_ms, 4000)

    def test_invalid_rate_context_rejected(self):
        for alignment in (AlignmentResult("none", D(0), D(0), (), ()),
                          AlignmentResult("zero", D(0), D(0), (WordInterval("x", D(0), D(0)),), ())):
            with self.assertRaises(ValueError):
                measure_utterance_rate(alignment, 20)
        for count in (0, -1, True):
            with self.assertRaises(ValueError):
                measure_utterance_rate(AlignmentResult("x", D(0), D(1), (WordInterval("x", D(0), D(1)),), ()), count)

    def test_uniform_time_scaling_invariant(self):
        profile = self.profile([("A", "fast", "150", "4000", "100", "1"),
                                ("B", "slow", "150", "4000", "100", "2")])
        fast, slow = [speaker.takes[0] for speaker in profile.speakers]
        self.assertEqual((fast.duration.raw_duration_ms, slow.duration.raw_duration_ms), (150, 300))
        self.assertEqual((fast.rate.mean_mora_period_ms, slow.rate.mean_mora_period_ms), (200, 400))
        self.assertEqual(fast.duration.rate_normalized_duration, slow.duration.rate_normalized_duration)
        self.assertEqual(fast.duration.rate_normalized_duration, D("0.75"))
        self.assertEqual(fast.duration.rate_normalized_duration_per_mora, D("0.375"))

    def test_normalization_uses_exact_ratio_not_rounded_display(self):
        span = LongVowelSpan("x", "c", 0, 0, "oː", D(0), D(1), (0, 1), VowelClass.O, MappingBasis.PROLONGED_MARK)
        alignment = AlignmentResult("a", D(0), D(1), (WordInterval("x", D(0), D(1)),), ())
        rate = measure_utterance_rate(alignment, 3)
        with localcontext() as context:
            context.prec = 2
            self.assertEqual(normalize_duration(span, rate).rate_normalized_duration, 3)

    def test_five_takes_one_speaker_plus_other_counts_two_speakers(self):
        profile = self.profile([("A", f"t{index}", str(100 + index * 10), "2000") for index in range(5)]
                               + [("B", "t0", "180", "2400")])
        self.assertEqual((len(profile.speakers), profile.to_dict()["take_count"]), (2, 6))
        self.assertEqual(profile.profile_status, "INSUFFICIENT_SPEAKERS")
        self.assertEqual(profile.speakers[0].to_dict()["valid_take_count"], 5)
        self.assertEqual(dict(profile.statistics)["raw_duration_ms"].count, 2)

    def test_speaker_feature_medians_then_equal_speaker_weight(self):
        profile = self.profile([("A", "t1", "100", "2000"), ("A", "t2", "200", "2000"),
                                ("A", "t3", "900", "2000"), ("B", "t1", "400", "2000")])
        self.assertEqual(dict(profile.speakers[0].medians)["raw_duration_ms"], 200)
        self.assertEqual(dict(profile.statistics)["raw_duration_ms"].median, 300)
        self.assertEqual(len(profile.speakers[0].takes), 3)

    def test_speaker_normalized_median_not_ratio_of_medians(self):
        profile = self.profile([("A", "a", "100", "4000"), ("A", "b", "300", "2000"),
                                ("A", "c", "400", "4000")])
        self.assertEqual(dict(profile.speakers[0].medians)["rate_normalized_duration"], 2)
        self.assertNotEqual(dict(profile.speakers[0].medians)["rate_normalized_duration"],
                            dict(profile.speakers[0].medians)["raw_duration_ms"]
                            / dict(profile.speakers[0].medians)["mean_mora_period_ms"])

    def test_known_median_mad_and_linear_iqr(self):
        stats = summarize(map(D, (1, 2, 3, 4, 100)))
        self.assertEqual((stats.count, stats.median, stats.mad, stats.q25, stats.q75, stats.iqr,
                          stats.minimum, stats.maximum), (5, 3, 1, 2, 4, 2, 1, 100))
        even = summarize(map(D, (1, 2, 3, 4)))
        self.assertEqual((even.median, even.mad, even.q25, even.q75, even.iqr),
                         (D("2.5"), 1, D("1.75"), D("3.25"), D("1.5")))

    def test_extreme_speaker_retained_without_moving_robust_center(self):
        profile = self.profile([(f"S{i}", "t", raw, "20000")
                                for i, raw in enumerate(("100", "110", "120", "130", "9000"))])
        stats = dict(profile.statistics)["raw_duration_ms"]
        self.assertEqual((stats.count, stats.median, stats.maximum), (5, 120, 9000))
        self.assertEqual(profile.speakers[-1].takes[0].duration.raw_duration_ms, 9000)

    def test_zero_mad_is_explicit_finite_zero(self):
        stats = summarize([D(100)] * 5)
        self.assertEqual((stats.mad, stats.iqr, stats.scale_status), (0, 0, "ZERO_MAD"))
        profile = self.profile()
        self.assertEqual(dict(profile.statistics)["rate_normalized_duration"].mad, 0)
        self.assertNotIn("NaN", profile.to_json())
        self.assertNotIn("Infinity", profile.to_json())

    def test_empty_summary_and_empty_profile(self):
        self.assertEqual(summarize([]).scale_status, "NO_OBSERVATIONS")
        self.assertIsNone(summarize([]).median)
        profile = self.profile([])
        self.assertEqual(profile.profile_status, "NO_VALID_OBSERVATIONS")
        self.assertEqual(profile.to_dict()["speaker_count"], 0)

    def test_nonfinite_or_float_statistics_rejected(self):
        for values in ([D("NaN")], [D("Infinity")], [1.2]):
            with self.assertRaises(ValueError):
                summarize(values)

    def test_configurable_engineering_readiness(self):
        profile = self.profile(minimum=5)
        self.assertEqual(profile.profile_status, "READY_FOR_EXPERIMENT")
        stricter = build_reference_profile(profile.manifest, ReferencePolicy(6))
        self.assertEqual(stricter.profile_status, "INSUFFICIENT_SPEAKERS")
        for minimum in (0, -1, True, 5.0):
            with self.assertRaises(ValueError):
                ReferencePolicy(minimum)

    def test_reference_schema_has_no_pitch_norm_or_diagnosis_fields(self):
        profile = self.profile()
        value = profile.to_dict()
        self.assertEqual(set(value["feature_statistics"]),
                         {"raw_duration_ms", "utterance_mora_rate_per_second", "mean_mora_period_ms",
                          "rate_normalized_duration", "rate_normalized_duration_per_mora"})
        forbidden = {"f0_hz", "raw_f0_hz", "native_f0", "learner", "score", "diagnosis", "severity",
                     "confidence", "correct_range", "normal_range", "wrong_range", "z_score"}
        def audit(item):
            if isinstance(item, dict):
                self.assertFalse(set(item) & forbidden)
                for part in item.values():
                    audit(part)
            if isinstance(item, list):
                for part in item:
                    audit(part)
        audit(value)
