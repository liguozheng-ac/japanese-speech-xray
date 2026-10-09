"""Authored deterministic waveforms only; no JVS or learner data."""
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest
import numpy as np
import soundfile as sf
from reference_test_support import ROOT
from speech_xray.stress.perturbation import manipulate, expected_samples, factor_fraction
from speech_xray.stress import FACTORS


class PerturbationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'authored.wav'
        time = np.arange(8000) / 8000
        signal = .15 * np.sin(2 * np.pi * 180 * time)
        sf.write(self.source, signal, 8000, subtype='PCM_16')

    def tearDown(self): self.temp.cleanup()

    def test_grid_sample_counts_and_unchanged_regions(self):
        original, _ = sf.read(self.source, dtype='int32', always_2d=True)
        for factor in FACTORS:
            with self.subTest(factor=factor):
                destination = self.root / (factor + '.wav')
                gt = manipulate(self.source, destination, 2000, 4000, factor)
                output, rate = sf.read(destination, dtype='int32', always_2d=True)
                size = expected_samples(2000, factor)
                self.assertEqual(gt['actual_perturbed_duration_samples'], size)
                self.assertEqual(gt['perturbed_target_sample_end'], 2000 + size)
                self.assertEqual(len(output), 6000 + size)
                self.assertTrue(np.array_equal(original[:2000], output[:2000]))
                self.assertTrue(np.array_equal(original[4000:], output[2000 + size:]))
                self.assertTrue(all(v for v in gt['integrity'].values() if v is not None))

    def test_control_is_byte_identical(self):
        destination = self.root / 'control.wav'
        gt = manipulate(self.source, destination, 2000, 4000, '1.00')
        self.assertEqual(self.source.read_bytes(), destination.read_bytes())
        self.assertEqual(gt['transition']['crossfade_samples_per_edge'], 0)

    def test_exact_rounding_half_up(self):
        self.assertEqual(expected_samples(5, '0.5'), 3)
        self.assertEqual(expected_samples(7, Fraction(1, 2)), 4)
        self.assertEqual(expected_samples(7, '1'), 7)

    def test_invalid_factor_rejected(self):
        for value in ('0', '-1', 'NaN', 'inf', True, .5, None, 'x'):
            with self.subTest(value=value), self.assertRaises(ValueError): factor_fraction(value)

    def test_empty_output_rejected(self):
        with self.assertRaises(ValueError): expected_samples(1, '0.2')

    def test_invalid_count_rejected(self):
        for count in (0, -1, True, 2.0):
            with self.assertRaises(ValueError): expected_samples(count, '1')

    def test_invalid_sample_range_rejected(self):
        for first, last in ((-1, 1), (2, 2), (1, 9000), (False, 2000)):
            with self.assertRaises(ValueError): manipulate(self.source, self.root/'invalid.wav', first, last, '.5')

    def test_existing_destination_rejected(self):
        with self.assertRaises(ValueError): manipulate(self.source, self.source, 2000, 4000, '.5')

    def test_crossfade_anchors_inside_target(self):
        path = self.root / 'crossfade.wav'
        gt = manipulate(self.source, path, 2000, 4000, '.5')
        original, _ = sf.read(self.source, dtype='int32')
        output, _ = sf.read(path, dtype='int32')
        self.assertEqual(gt['transition']['external_guard_samples'], 0)
        self.assertEqual(original[2000], output[2000])
        self.assertEqual(original[3999], output[2999])

    def test_boundary_at_whole_audio_edges(self):
        gt = manipulate(self.source, self.root/'edges.wav', 0, 8000, '.5')
        self.assertEqual(gt['artifacts']['boundary_jump_after'], [None, None])

    def test_stereo_and_pcm_depth_preserved(self):
        for subtype in ('PCM_16', 'PCM_24', 'PCM_32'):
            path = self.root / (subtype + '.wav')
            signal = np.zeros((4000, 2));signal[:, 0] = .1 * np.sin(np.arange(4000) * .1)
            sf.write(path, signal, 8000, subtype=subtype)
            gt = manipulate(path, self.root/(subtype+'-out.wav'), 1000, 3000, '1.25')
            self.assertEqual(gt['channels'], 2);self.assertEqual(gt['pcm_subtype'], subtype)

    def test_zero_signal_finite_and_no_normalization(self):
        path = self.root/'silent.wav';sf.write(path, np.zeros(4000), 8000, subtype='PCM_16')
        gt = manipulate(path, self.root/'silent-out.wav', 1000, 3000, '.2')
        self.assertEqual(gt['normalization']['local_pre_crossfade_safety_gains'], [1.0])
        self.assertFalse(gt['normalization']['global_loudness_normalization'])

    def test_sha_and_provenance_repeatable(self):
        first = manipulate(self.source, self.root/'one.wav', 2000, 4000, '.8')
        second = manipulate(self.source, self.root/'two.wav', 2000, 4000, '.8')
        self.assertEqual(first, second)
        self.assertEqual(first['requested_duration_factor'], {'numerator': 4, 'denominator': 5})

    def test_float_wav_rejected(self):
        path = self.root/'float.wav';sf.write(path, np.zeros(4000), 8000, subtype='FLOAT')
        with self.assertRaises(ValueError): manipulate(path, self.root/'float-out.wav', 1000, 3000, '.5')
