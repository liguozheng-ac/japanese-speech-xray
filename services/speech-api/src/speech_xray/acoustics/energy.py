"""Time-domain RMS on the same windows as pYIN, in decoded amplitude units."""

import librosa
import numpy as np
from .config import AcousticConfig


def extract_rms(samples: np.ndarray, config: AcousticConfig) -> np.ndarray:
    return librosa.feature.rms(y=samples, frame_length=config.frame_length, hop_length=config.hop_length,
                              center=config.center, pad_mode=config.pad_mode, dtype=np.float64)[0]
