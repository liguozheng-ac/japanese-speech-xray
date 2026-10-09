"""Extract once per utterance, retaining each padded frame's sample coordinates."""

import warnings
import numpy as np

from .audio import AudioData
from .config import AcousticConfig
from .energy import extract_rms
from .f0 import extract_f0
from .models import AcousticFrame, AcousticTrack, ExtractionStatus as Status
from .timing import sample_time_ms


def extract_track(audio: AudioData, config: AcousticConfig = AcousticConfig()) -> AcousticTrack:
    rate, size = audio.metadata.sample_rate_hz, len(audio.samples)
    if not config.center and size < config.frame_length:
        return AcousticTrack(rate, size, (), Status.NO_FRAMES, Status.INSUFFICIENT_AUDIO_FOR_F0,
                             ("No complete unpadded analysis window",))
    expected = 1 + (size if config.center else size - config.frame_length) // config.hop_length
    messages = []
    try:
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            rms = extract_rms(audio.samples, config)
        messages.extend(str(warning.message) for warning in captured)
        if rms.shape != (expected,) or not np.isfinite(rms).all() or np.any(rms < 0):
            raise ValueError("Invalid RMS values or frame count")
    except Exception as error:
        return AcousticTrack(rate, size, (), Status.ENERGY_EXTRACTION_FAILED, Status.NO_FRAMES,
                             (f"RMS failed: {type(error).__name__}: {error}",))

    f0 = voiced = probability = None
    if size < config.frame_length:
        f0_status = Status.INSUFFICIENT_AUDIO_FOR_F0
        messages.append("Audio cannot provide one complete unpadded F0 window; RMS retained")
    elif (config.fmax_hz >= rate / 2 or config.frame_length <= 2 * rate / config.fmin_hz):
        f0_status = Status.F0_CONFIG_UNSUPPORTED
        messages.append("F0 bounds/window incompatible with original sample rate; no resampling performed")
    else:
        try:
            with warnings.catch_warnings(record=True) as captured:
                warnings.simplefilter("always")
                f0, voiced, probability = extract_f0(audio.samples, rate, config)
            messages.extend(str(warning.message) for warning in captured)
            if any(part.shape != (expected,) for part in (f0, voiced, probability)):
                raise ValueError("F0/RMS timelines have different frame counts")
            if (voiced.dtype != np.bool_ or not np.isfinite(probability).all()
                    or np.any((probability < 0) | (probability > 1))
                    or not np.isfinite(f0[voiced]).all() or np.any(f0[voiced] <= 0)):
                raise ValueError("Invalid upstream voiced F0 or voicing probability")
            f0_status = Status.OK
        except Exception as error:
            f0, voiced, probability = None, None, None
            f0_status = Status.F0_EXTRACTION_FAILED
            messages.append(f"pYIN failed: {type(error).__name__}: {error}")

    frames = []
    for index, value in enumerate(rms):
        start = index * config.hop_length - (config.frame_length // 2 if config.center else 0)
        center = start + config.frame_length // 2
        end = start + config.frame_length
        flag = bool(voiced[index]) if voiced is not None else None
        frames.append(AcousticFrame(
            index, start, center, end, max(0, start), min(size, end), max(0, -start), max(0, end - size),
            sample_time_ms(start, rate), sample_time_ms(center, rate), sample_time_ms(end, rate),
            float(f0[index]) if flag else None, flag,
            float(probability[index]) if probability is not None else None, float(value)))
    status = (Status.OK if any(frame.voiced for frame in frames) else Status.NO_VOICED_FRAMES
              ) if f0_status == Status.OK else f0_status
    return AcousticTrack(rate, size, tuple(frames), status, f0_status, tuple(dict.fromkeys(messages)))
