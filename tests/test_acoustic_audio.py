"""Audio metadata and integrity tests; all signals generated at runtime."""

import hashlib
from pathlib import Path
import tempfile
import unittest
import numpy as np
import soundfile as sf
from acoustic_test_support import ROOT, tone, write_wav
from speech_xray.acoustics.audio import InvalidAudioError, load_audio
from speech_xray.acoustics.config import AcousticConfig


class AcousticAudioTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".tools/tmp").mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=ROOT / ".tools/tmp")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)

    def test_original_rate_metadata_and_hash(self):
        path = write_wav(self.path / "tone.wav", tone(rate=24000, size=12000), rate=24000)
        original = path.read_bytes()
        audio = load_audio(path)
        self.assertEqual(audio.metadata.sample_rate_hz, 24000)
        self.assertEqual(audio.metadata.channels, 1)
        self.assertEqual(audio.metadata.frame_count, 12000)
        self.assertEqual(audio.metadata.duration_ms, 500)
        self.assertEqual(audio.metadata.subtype, "FLOAT")
        self.assertEqual(audio.metadata.sha256, hashlib.sha256(original).hexdigest())
        self.assertFalse(audio.metadata.resampled)
        self.assertFalse(audio.samples.flags.writeable)
        self.assertEqual(path.read_bytes(), original)

    def test_stereo_mean_preserves_original_channels(self):
        signal = tone()
        path = write_wav(self.path / "stereo.wav", np.column_stack((signal, signal * 0.5)))
        audio = load_audio(path)
        self.assertEqual(audio.metadata.channels, 2)
        self.assertEqual(audio.metadata.analysis_mono_strategy, "ARITHMETIC_MEAN_FLOAT64")
        np.testing.assert_allclose(audio.samples, signal * 0.75, atol=1e-8)
        self.assertGreater(audio.metadata.original_peak_abs_amplitude, audio.metadata.analysis_peak_abs_amplitude)

    def test_stereo_cancellation_is_explicit_mean(self):
        signal = tone()
        path = write_wav(self.path / "cancel.wav", np.column_stack((signal, -signal)))
        audio = load_audio(path)
        self.assertTrue(np.all(audio.samples == 0))
        self.assertGreater(audio.metadata.original_peak_abs_amplitude, 0)
        self.assertEqual(audio.metadata.analysis_peak_abs_amplitude, 0)

    def test_silence_is_valid_audio(self):
        audio = load_audio(write_wav(self.path / "silence.wav", np.zeros(8000)))
        self.assertEqual(audio.metadata.original_peak_abs_amplitude, 0)

    def test_invalid_missing_empty_and_nonfinite_audio(self):
        missing = self.path / "missing.wav"
        broken = self.path / "broken.wav"
        broken.write_bytes(b"not a WAV")
        empty = write_wav(self.path / "empty.wav", np.zeros(0))
        nonfinite = write_wav(self.path / "nonfinite.wav", np.array([0.0, np.nan, np.inf]))
        for path in (missing, broken, empty, nonfinite):
            with self.subTest(path=path.name), self.assertRaises(InvalidAudioError):
                load_audio(path)

    def test_non_wav_is_not_silently_accepted(self):
        path = self.path / "signal.flac"
        sf.write(path, tone(), 16000, format="FLAC")
        with self.assertRaises(InvalidAudioError):
            load_audio(path)

    def test_configuration_is_immutable_and_validated(self):
        config = AcousticConfig()
        with self.assertRaises(AttributeError):
            config.hop_length = 100
        for kwargs in ({"frame_length": 255}, {"hop_length": 0}, {"fmin_hz": 600},
                       {"fmax_hz": float("inf")}, {"mono_strategy": "pick-a-channel"},
                       {"center": "yes"}, {"pad_mode": "reflect"}, {"switch_prob": 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                AcousticConfig(**kwargs)


if __name__ == "__main__":
    unittest.main()
