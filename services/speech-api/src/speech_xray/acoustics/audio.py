"""Read an unchanged WAV snapshot at its original rate and hash those exact bytes."""

from dataclasses import dataclass
import hashlib
from io import BytesIO
from pathlib import Path
import numpy as np
import soundfile as sf
from .models import AudioMetadata
from .timing import sample_time_ms


class InvalidAudioError(ValueError):
    pass


@dataclass(frozen=True)
class AudioData:
    metadata: AudioMetadata
    samples: np.ndarray


def load_audio(path: str | Path) -> AudioData:
    source = Path(path).resolve()
    try:
        raw = source.read_bytes()
        info = sf.info(BytesIO(raw))
        samples, rate = sf.read(BytesIO(raw), dtype="float64", always_2d=True)
    except (OSError, sf.LibsndfileError, ValueError) as error:
        raise InvalidAudioError(f"Unreadable WAV: {type(error).__name__}") from error
    if info.format not in {"WAV", "WAVEX", "RF64"} or info.frames <= 0 or info.channels <= 0:
        raise InvalidAudioError("Expected nonempty WAV-family audio")
    if rate != info.samplerate or samples.shape != (info.frames, info.channels):
        raise InvalidAudioError("Decoded samples do not match original header")
    if not np.isfinite(samples).all():
        raise InvalidAudioError("Audio contains non-finite samples")
    mono = np.ascontiguousarray(np.mean(samples, axis=1, dtype=np.float64))
    if not np.isfinite(mono).all():
        raise InvalidAudioError("Channel mean contains non-finite samples")
    mono.flags.writeable = False
    metadata = AudioMetadata(str(source), hashlib.sha256(raw).hexdigest(), rate, info.channels,
                             info.frames, sample_time_ms(info.frames, rate), info.format, info.subtype,
                             "IDENTITY_MONO_FLOAT64" if info.channels == 1 else "ARITHMETIC_MEAN_FLOAT64",
                             float(np.max(np.abs(samples))), float(np.max(np.abs(mono))))
    return AudioData(metadata, mono)
