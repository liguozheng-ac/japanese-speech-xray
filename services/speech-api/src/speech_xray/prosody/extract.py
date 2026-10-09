"""Actual pYIN frames at the original PCM rate; no phoneme boundaries or models."""
from hashlib import sha256
from io import BytesIO
import logging
from time import perf_counter
import importlib.metadata
import numpy as np
import soundfile as sf
from speech_xray.product.errors import ProductError

VERSION = 'prosody-pyin-1'
PARAMETERS = dict(fmin=50., fmax=600., n_thresholds=100, beta_parameters=(2, 18),
                  boltzmann_parameter=2., resolution=.1, max_transition_rate=35.92,
                  switch_prob=.01, no_trough_prob=.01, transition_min_prob=.0001,
                  center=True, pad_mode='constant')
ENERGY_FLOOR_DBFS = -60.
MIN_VOICED_PROBABILITY = .1  # Display admission only; not calibrated accent accuracy.


def decode_wav(raw, settings):
    """Bounded in-memory admission with the product's strict mono PCM16 domain.

    This does not change the existing upload validator or convert channels.
    """
    if len(raw) > settings.max_upload_bytes:
        raise ProductError('UPLOAD_TOO_LARGE', 'INPUT_VALIDATED', 'UPLOAD_LIMIT')
    if len(raw) < 12:
        raise ProductError('INVALID_AUDIO', 'INPUT_VALIDATED', 'INVALID_HEADER')
    if raw[:4] != b'RIFF' or raw[8:12] != b'WAVE':
        raise ProductError('UNSUPPORTED_FORMAT', 'INPUT_VALIDATED', 'WAV_REQUIRED')
    try:
        info = sf.info(BytesIO(raw))
    except (ValueError, OSError, sf.LibsndfileError) as error:
        raise ProductError('INVALID_AUDIO', 'INPUT_VALIDATED', 'DECODE_FAILED') from error
    if info.format != 'WAV' or info.subtype != 'PCM_16' or info.channels != 1:
        raise ProductError('UNSUPPORTED_FORMAT', 'INPUT_VALIDATED', 'MONO_PCM16_REQUIRED')
    if info.frames <= 0 or not 8000 <= info.samplerate <= 48000:
        raise ProductError('INVALID_AUDIO', 'INPUT_VALIDATED', 'INVALID_AUDIO_DOMAIN')
    if info.frames * 1000 > settings.max_duration_ms * info.samplerate:
        raise ProductError('AUDIO_TOO_LONG', 'INPUT_VALIDATED', 'DURATION_LIMIT')
    try:
        samples, rate = sf.read(BytesIO(raw), dtype='float64', always_2d=False)
        if rate != info.samplerate or samples.shape != (info.frames,) or not np.isfinite(samples).all():
            raise ValueError('DECODE_SHAPE_OR_VALUES')
    except (ValueError, OSError, sf.LibsndfileError) as error:
        raise ProductError('INVALID_AUDIO', 'INPUT_VALIDATED', 'DECODE_FAILED') from error
    return samples, rate


def extract(raw, settings):
    samples, rate = decode_wav(raw, settings)
    started = perf_counter()
    # At least 80 ms / two 50 Hz periods. No sample-rate or amplitude conversion.
    frame_length = 2 ** int(np.ceil(np.log2(rate * .08)))
    hop = round(rate * .02)
    duration = len(samples) / rate
    parameters = {**PARAMETERS, 'sample_rate_hz': rate, 'frame_length': frame_length,
                  'hop_length': hop, 'hop_ms': hop * 1000 / rate, 'resampling': 'NONE',
                  'energy_floor_dbfs': ENERGY_FLOOR_DBFS, 'min_voiced_probability': MIN_VOICED_PROBABILITY,
                  'fill_na': 'NaN converted to JSON null'}
    row = dict(status='ABSTAINED', reason=None, audio_sha256=sha256(raw).hexdigest(),
               duration_ms=duration * 1000, sample_rate_hz=rate, sample_count=len(samples),
               parameters=parameters, frames=[], observations=None, extraction_ms=0.)
    try:
        import librosa
        if importlib.metadata.version('librosa') != '1.0.0':
            raise ValueError('LIBROSA_VERSION_CHANGED')
        rms = librosa.feature.rms(y=samples, frame_length=frame_length, hop_length=hop,
                                  center=True, pad_mode='constant')[0]
        times = np.arange(len(rms)) * hop / rate
        inside = times < duration
        rms, times = rms[inside], times[inside]
        db = 20 * np.log10(np.maximum(rms, 1e-6))
        row['frames'] = [dict(time_ms=float(t * 1000), f0_hz=None, voiced=False,
                              pyin_voiced=None, voiced_probability=None, rms_dbfs=float(d))
                         for t, d in zip(times, db)]
        if len(samples) < frame_length:
            row['reason'] = 'AUDIO_TOO_SHORT_FOR_F0'
        elif float(np.max(rms)) <= 10 ** (ENERGY_FLOOR_DBFS / 20):
            row['reason'] = 'LOW_ENERGY_NO_F0'
        else:
            f0, flags, probability = librosa.pyin(samples, sr=rate, frame_length=frame_length,
                                                 hop_length=hop, fill_na=np.nan, **PARAMETERS)
            expected = 1 + len(samples) // hop
            if any(a.shape != (expected,) for a in (f0, flags, probability)):
                raise ValueError('PYIN_FRAME_SHAPE')
            if flags.dtype != np.bool_ or not np.isfinite(probability).all() or np.any((probability < 0) | (probability > 1)):
                raise ValueError('PYIN_VOICING_INVALID')
            if not np.isfinite(f0[flags]).all() or np.any((f0[flags] < PARAMETERS['fmin']) | (f0[flags] > PARAMETERS['fmax'])):
                raise ValueError('PYIN_F0_INVALID')
            f0, flags, probability = f0[inside], flags[inside], probability[inside]
            # Retain upstream voicing evidence, while excluding almost-silent frames.
            voiced = flags & (db > ENERGY_FLOOR_DBFS) & (probability >= MIN_VOICED_PROBABILITY)
            for i, frame in enumerate(row['frames']):
                frame.update(f0_hz=float(f0[i]) if voiced[i] else None, voiced=bool(voiced[i]),
                             pyin_voiced=bool(flags[i]), voiced_probability=float(probability[i]))
            row['status'] = 'AVAILABLE' if int(voiced.sum()) >= 5 else 'ABSTAINED'
            row['reason'] = None if row['status'] == 'AVAILABLE' else 'INSUFFICIENT_VOICED_FRAMES'
            if row['status'] != 'AVAILABLE':
                for frame in row['frames']:
                    frame.update(f0_hz=None, voiced=False)
    except Exception as error:
        logging.getLogger('speech_xray.prosody').warning('f0_abstained reason=%s message=%s', type(error).__name__, str(error))
        row.update(status='ABSTAINED', reason='F0_EXTRACTION_FAILED')
        for frame in row['frames']:
            frame.update(f0_hz=None, voiced=False)
    voiced_frames = [f for f in row['frames'] if f['voiced']]
    if voiced_frames:
        values = np.array([f['f0_hz'] for f in voiced_frames])
        early = [f['f0_hz'] for f in voiced_frames if f['time_ms'] < duration * 1000 / 3]
        late = [f['f0_hz'] for f in voiced_frames if f['time_ms'] > duration * 1000 * 2 / 3]
        row['observations'] = dict(median_f0_hz=float(np.median(values)),
            p10_f0_hz=float(np.percentile(values, 10)), p90_f0_hz=float(np.percentile(values, 90)),
            voiced_fraction=len(voiced_frames) / len(row['frames']),
            median_voiced_probability=float(np.median([f['voiced_probability'] for f in voiced_frames])),
            late_minus_early_semitones=float(12 * np.log2(np.median(late) / np.median(early))) if len(early) >= 5 and len(late) >= 5 else None)
    row['extraction_ms'] = (perf_counter() - started) * 1000
    return row
