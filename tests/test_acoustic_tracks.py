"""DSP checks on mathematical signals, not pronunciation benchmarks."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

from acoustic_test_support import ROOT, tone, write_wav, analysis
from speech_xray.acoustics.audio import load_audio
from speech_xray.acoustics.config import AcousticConfig
from speech_xray.acoustics.models import ExtractionStatus as Status
from speech_xray.acoustics.pipeline import extract_acoustic_evidence
from speech_xray.acoustics.tracks import extract_track


class AcousticTrackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / ".tools/tmp").mkdir(parents=True, exist_ok=True)
        cls.directory = tempfile.TemporaryDirectory(dir=ROOT / ".tools/tmp")
        cls.addClassCleanup(cls.directory.cleanup)
        cls.path = Path(cls.directory.name)
        cls.high = load_audio(write_wav(cls.path / "high.wav", tone(amplitude=0.2)))
        cls.low = load_audio(write_wav(cls.path / "low.wav", tone(amplitude=0.05)))
        cls.silent = load_audio(write_wav(cls.path / "silence.wav", np.zeros(8000)))
        cls.track = extract_track(cls.high)
        cls.low_track = extract_track(cls.low)
        cls.silent_track = extract_track(cls.silent)

    def voiced_median(self, track):
        return float(np.median([frame.f0_hz for frame in track.frames if frame.voiced]))

    def test_known_sine_has_raw_f0_near_frequency(self):
        self.assertEqual(self.track.extraction_status, Status.OK)
        self.assertGreater(sum(frame.voiced is True for frame in self.track.frames), 0)
        self.assertLess(abs(self.voiced_median(self.track) - 220), 220 * 0.03)

    def test_monotonic_timestamps_padding_and_sample_coordinates(self):
        centers = [frame.center_sample for frame in self.track.frames]
        self.assertEqual(centers, list(range(0, 8001, 256)))
        self.assertTrue(all(left.frame_center_ms < right.frame_center_ms
                            for left, right in zip(self.track.frames, self.track.frames[1:])))
        first = self.track.frames[0]
        self.assertEqual((first.window_start_sample, first.center_sample, first.window_end_sample), (-1024, 0, 1024))
        self.assertEqual(first.padding_left_samples, 1024)
        self.assertEqual(first.observed_start_sample, 0)
        self.assertLess(first.frame_start_ms, 0)
        self.assertGreater(self.track.frames[-1].padding_right_samples, 0)

    def test_all_available_values_finite_and_probability_not_diagnosis(self):
        for frame in self.track.frames:
            self.assertTrue(np.isfinite(frame.rms))
            self.assertTrue(np.isfinite(frame.voicing_probability))
            self.assertGreaterEqual(frame.voicing_probability, 0)
            self.assertLessEqual(frame.voicing_probability, 1)
            self.assertEqual(frame.f0_hz is not None, frame.voiced)
            self.assertNotIn("confidence", frame.to_dict())

    def test_silence_null_f0_zero_rms_without_nonfinite_json(self):
        self.assertEqual(self.silent_track.extraction_status, Status.NO_VOICED_FRAMES)
        self.assertTrue(all(frame.f0_hz is None and frame.voiced is False for frame in self.silent_track.frames))
        self.assertTrue(all(frame.rms == 0 for frame in self.silent_track.frames))
        result = extract_acoustic_evidence(self.path / "silence.wav", analysis())
        text = result.to_json()
        self.assertNotIn("NaN", text)
        self.assertNotIn("Infinity", text)
        json.loads(text, parse_constant=lambda value: self.fail(value))
        self.assertEqual(result.spans[0].voiced_frame_ratio, 0)
        self.assertIsNone(result.spans[0].raw_f0_hz.median)

    def test_amplitude_changes_rms_without_changing_pitch(self):
        self.assertLess(abs(self.voiced_median(self.track) - self.voiced_median(self.low_track)), 220 * 0.02)
        # Interior windows only, avoiding edge padding; amplitude ratio is exactly four.
        high = np.median([frame.rms for frame in self.track.frames if not frame.padding_left_samples and not frame.padding_right_samples])
        low = np.median([frame.rms for frame in self.low_track.frames if not frame.padding_left_samples and not frame.padding_right_samples])
        self.assertAlmostEqual(float(high / low), 4.0, places=5)
        self.assertLess(abs(float(high) - 0.2 / np.sqrt(2)), 0.002)

    def test_short_audio_keeps_rms_but_f0_unavailable(self):
        short = load_audio(write_wav(self.path / "short.wav", tone(size=20)))
        track = extract_track(short)
        self.assertEqual(track.extraction_status, Status.INSUFFICIENT_AUDIO_FOR_F0)
        self.assertEqual(len(track.frames), 1)
        self.assertIsNone(track.frames[0].voiced)
        self.assertIsNone(track.frames[0].voicing_probability)
        self.assertIsNone(track.frames[0].f0_hz)
        self.assertTrue(np.isfinite(track.frames[0].rms))
        uncentered = extract_track(short, AcousticConfig(center=False))
        self.assertEqual(uncentered.extraction_status, Status.NO_FRAMES)

    def test_center_false_windows_are_unpadded(self):
        track = extract_track(self.high, AcousticConfig(center=False))
        self.assertEqual(len(track.frames), 1 + (8000 - 2048) // 256)
        self.assertEqual(track.frames[0].center_sample, 1024)
        self.assertEqual(track.frames[0].window_start_sample, 0)
        self.assertTrue(all(frame.padding_left_samples == frame.padding_right_samples == 0 for frame in track.frames))

    def test_f0_backend_failure_preserves_rms_and_unknown_voicing(self):
        with patch("speech_xray.acoustics.tracks.extract_f0", side_effect=RuntimeError("test backend failure")):
            track = extract_track(self.high)
        self.assertEqual(track.extraction_status, Status.F0_EXTRACTION_FAILED)
        self.assertTrue(track.frames)
        self.assertTrue(all(frame.voiced is None and frame.f0_hz is None for frame in track.frames))

    def test_f0_config_incompatible_with_rate_has_structured_status(self):
        track = extract_track(self.high, AcousticConfig(frame_length=128, hop_length=32))
        self.assertEqual(track.extraction_status, Status.F0_CONFIG_UNSUPPORTED)
        self.assertTrue(track.frames)

    def test_invalid_upstream_values_and_energy_failure_do_not_escape_as_nonfinite(self):
        count = len(self.track.frames)
        invalid = (np.full(count, np.nan), np.ones(count, dtype=bool), np.ones(count))
        with patch("speech_xray.acoustics.tracks.extract_f0", return_value=invalid):
            track = extract_track(self.high)
        self.assertEqual(track.extraction_status, Status.F0_EXTRACTION_FAILED)
        self.assertTrue(all(frame.f0_hz is None for frame in track.frames))
        with patch("speech_xray.acoustics.tracks.extract_rms", return_value=np.full(count, np.inf)):
            track = extract_track(self.high)
        self.assertEqual(track.extraction_status, Status.ENERGY_EXTRACTION_FAILED)
        self.assertEqual(track.frames, ())

    def test_pipeline_runs_f0_once_for_multiple_existing_spans(self):
        from dataclasses import replace
        from speech_xray.acoustics.mora_input import MoraSpanInput
        from speech_xray.acoustics.f0 import extract_f0
        first = analysis().long_vowel_spans[0]
        second = replace(first, id="another-span", phone_index=2)
        with patch("speech_xray.acoustics.tracks.extract_f0", wraps=extract_f0) as backend:
            result = extract_acoustic_evidence(self.path / "high.wav", MoraSpanInput("authored", (first, second)))
        self.assertEqual(backend.call_count, 1)
        self.assertEqual(len(result.spans), 2)
        self.assertEqual(result.spans[0].selected_frame_indices, result.spans[1].selected_frame_indices)


if __name__ == "__main__":
    unittest.main()
