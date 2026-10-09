"""Only upstream pYIN estimates raw pitch and voicing."""

import librosa
import numpy as np
from .config import AcousticConfig


def extract_f0(samples: np.ndarray, sample_rate: int, config: AcousticConfig):
    return librosa.pyin(
        samples, sr=sample_rate, frame_length=config.frame_length, hop_length=config.hop_length,
        fmin=config.fmin_hz, fmax=config.fmax_hz, center=config.center, pad_mode=config.pad_mode,
        n_thresholds=config.n_thresholds, beta_parameters=config.beta_parameters,
        boltzmann_parameter=config.boltzmann_parameter, resolution=config.resolution,
        max_transition_rate=config.max_transition_rate, switch_prob=config.switch_prob,
        no_trough_prob=config.no_trough_prob, transition_min_prob=config.transition_min_prob,
        fill_na=np.nan)
