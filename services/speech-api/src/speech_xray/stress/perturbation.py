"""Local phase-vocoder duration changes; ground truth is independent of MFA."""
from fractions import Fraction
from importlib.metadata import version
from pathlib import Path
import hashlib
import shutil
import numpy as np
import soundfile as sf
import librosa

from speech_xray.corpus.batch_plan import digest
from . import MATERIAL_KIND

BITS = {'PCM_16': 16, 'PCM_24': 24, 'PCM_32': 32}


def factor_fraction(value):
    if isinstance(value, (bool, float)):
        raise ValueError('FACTOR_REQUIRES_EXACT_DECIMAL_OR_RATIONAL')
    try:
        result = Fraction(value)
    except (ValueError, TypeError, ZeroDivisionError, OverflowError) as error:
        raise ValueError('INVALID_DURATION_FACTOR') from error
    if result <= 0:
        raise ValueError('DURATION_FACTOR_MUST_BE_POSITIVE')
    return result


def expected_samples(count, factor):
    if type(count) is not int or count <= 0:
        raise ValueError('ORIGINAL_SAMPLE_COUNT_MUST_BE_POSITIVE_INTEGER')
    value = count * factor_fraction(factor)
    result = (2 * value.numerator + value.denominator) // (2 * value.denominator)
    if result < 1:
        raise ValueError('PERTURBED_REGION_WOULD_BE_EMPTY')
    return result


def rational(value):
    value = Fraction(value)
    return {'numerator': value.numerator, 'denominator': value.denominator}


def samples_hash(samples):
    return hashlib.sha256(np.ascontiguousarray(samples, dtype='<i4').tobytes()).hexdigest()


def manipulate(source, destination, start, end, factor, crossfade_ms=5, n_fft=512, hop_length=128):
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve() or destination.exists():
        raise ValueError('AUDIO_DESTINATION_MUST_BE_NEW')
    if (type(start) is not int or type(end) is not int or type(crossfade_ms) is not int
            or crossfade_ms < 0 or type(n_fft) is not int or n_fft < 4 or n_fft % 2
            or type(hop_length) is not int or not 0 < hop_length <= n_fft):
        raise ValueError('INVALID_SAMPLE_OR_STRETCH_CONFIGURATION')
    info = sf.info(source)
    if info.format != 'WAV' or info.subtype not in BITS:
        raise ValueError('SUPPORTED_PCM_WAV_REQUIRED')
    pcm, rate = sf.read(source, dtype='int32', always_2d=True)
    if not 0 <= start < end <= len(pcm):
        raise ValueError('TARGET_SAMPLE_RANGE_OUTSIDE_WAV')
    count = end - start
    f = factor_fraction(factor)
    size = expected_samples(count, f)
    original = pcm[start:end].astype(np.float64) / 2**31
    guard = 0 if f == 1 else min(rate * crossfade_ms // 1000, count // 3, size // 3)
    gains, pre_peaks = [], []
    if f == 1:
        replacement = pcm[start:end].copy()
        output = pcm.copy()
    else:
        # librosa's rate is speed, reciprocal to the requested duration factor.
        # Original/expected sample counts remove fractional rounding ambiguity.
        modified = np.stack([librosa.effects.time_stretch(original[:, channel],
            rate=count / size, n_fft=n_fft, hop_length=hop_length, center=True)
            for channel in range(info.channels)], axis=1)
        if modified.shape != (size, info.channels) or not np.isfinite(modified).all():
            raise ValueError('STRETCH_SAMPLE_COUNT_OR_FINITE_CHECK_FAILED')
        ceiling = 1 - 1 / 2**(BITS[info.subtype] - 1)
        for channel in range(info.channels):
            peak = float(np.max(np.abs(modified[:, channel])))
            gain = min(1.0, ceiling / peak) if peak else 1.0
            pre_peaks.append(peak); gains.append(gain)
            modified[:, channel] *= gain
        if guard:
            ramp = np.linspace(0, 1, guard)[:, None]
            modified[:guard] = original[:guard] * (1 - ramp) + modified[:guard] * ramp
            modified[-guard:] = modified[-guard:] * (1 - ramp) + original[-guard:] * ramp
        step = 2**(32 - BITS[info.subtype])
        quantized = np.rint(modified * 2**31 / step) * step
        if (not np.isfinite(quantized).all() or np.any(quantized > 2**31 - step)
                or np.any(quantized < -2**31)):
            raise ValueError('PCM_CLIPPING_WOULD_BE_INTRODUCED')
        replacement = quantized.astype(np.int32)
        output = np.concatenate((pcm[:start], replacement, pcm[end:]), axis=0)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if f == 1:
        shutil.copyfile(source, destination)
    else:
        sf.write(destination, output, rate, subtype=info.subtype, format='WAV')
    decoded, decoded_rate = sf.read(destination, dtype='int32', always_2d=True)
    read_info = sf.info(destination)
    checks = {'sample_rate_unchanged': decoded_rate == rate, 'channels_unchanged': read_info.channels == info.channels,
        'pcm_format_unchanged': (read_info.format, read_info.subtype) == (info.format, info.subtype),
        'finite_samples': bool(np.isfinite(decoded).all()), 'expected_total_sample_count': len(decoded) == len(pcm) - count + size,
        'unchanged_prefix': np.array_equal(decoded[:start], pcm[:start]),
        'unchanged_shifted_suffix': np.array_equal(decoded[start + size:], pcm[end:]),
        'decoded_output_matches_written_pcm': np.array_equal(decoded, output),
        'factor_one_byte_identity': digest(source) == digest(destination) if f == 1 else None}
    if not all(value for value in checks.values() if value is not None):
        raise ValueError('PERTURBED_AUDIO_INTEGRITY_FAILED')
    as_float = replacement.astype(np.float64) / 2**31
    jumps = []
    for position in (start, start + size):
        jumps.append(float(np.max(np.abs((decoded[position].astype(np.float64) - decoded[position - 1]) / 2**31)))
                     if 0 < position < len(decoded) else None)
    originals = [float(np.max(np.abs((pcm[p].astype(np.float64) - pcm[p-1]) / 2**31)))
                 if 0 < p < len(pcm) else None for p in (start, end)]
    return {'schema_version': '0.1', 'material_kind': MATERIAL_KIND, 'representation': 'MANIPULATION_GROUND_TRUTH',
        'input_audio_sha256': digest(source), 'output_audio_sha256': digest(destination),
        'sample_rate_hz': rate, 'channels': info.channels, 'pcm_subtype': info.subtype,
        'original_frame_count': len(pcm), 'output_frame_count': len(decoded),
        'original_target_sample_start': start, 'original_target_sample_end': end, 'original_duration_samples': count,
        'requested_duration_factor': rational(f), 'requested_factor_decimal': str(factor),
        'expected_perturbed_duration_samples': size, 'actual_perturbed_duration_samples': len(replacement),
        'perturbed_target_sample_start': start, 'perturbed_target_sample_end': start + size,
        'exact_original_duration_seconds': rational(Fraction(count, rate)),
        'exact_perturbed_duration_seconds': rational(Fraction(size, rate)),
        'algorithm': {'name': 'LIBROSA_EFFECTS_TIME_STRETCH_PHASE_VOCODER', 'librosa_version': version('librosa'),
            'soundfile_version': version('soundfile'), 'numpy_version': version('numpy'),
            'requested_speed': rational(Fraction(count, size)), 'n_fft': n_fft, 'hop_length': hop_length, 'center': True,
            'sample_rounding': 'NEAREST_INTEGER_HALF_UP', 'control_policy': 'UNCHANGED_FILE_COPY',
            'pitch_intent': 'NO_INTENTIONAL_PITCH_SHIFT_NO_PERFECT_F0_PRESERVATION_CLAIM'},
        'transition': {'crossfade_ms_requested': crossfade_ms, 'crossfade_samples_per_edge': guard,
            'crossfade_location': 'INSIDE_TARGET_ONLY', 'external_guard_samples': 0,
            'unchanged_prefix_samples': start, 'unchanged_shifted_suffix_samples': len(pcm) - end},
        'normalization': {'global_loudness_normalization': False, 'local_pre_crossfade_safety_gains': gains,
            'policy': 'ATTENUATE_ONLY_STRETCHED_REGION_IF_PCM_RANGE_WOULD_OVERFLOW', 'hard_clipped_samples': 0},
        'sample_hashes': {'original_prefix': samples_hash(pcm[:start]), 'output_prefix': samples_hash(decoded[:start]),
            'original_suffix': samples_hash(pcm[end:]), 'output_shifted_suffix': samples_hash(decoded[start + size:])},
        'integrity': checks, 'artifacts': {'boundary_jump_before': originals, 'boundary_jump_after': jumps,
            'pre_attenuation_channel_peaks': pre_peaks, 'target_peak_before': float(np.max(np.abs(original))),
            'target_peak_after': float(np.max(np.abs(as_float))),
            'target_rms_before': float(np.sqrt(np.mean(original**2))),
            'target_rms_after': float(np.sqrt(np.mean(as_float**2)))}}
