"""Extraction bounds and settings, never pronunciation criteria."""

from dataclasses import asdict, dataclass
import math


@dataclass(frozen=True)
class AcousticConfig:
    frame_length: int = 2048
    hop_length: int = 256
    fmin_hz: float = 50.0
    fmax_hz: float = 500.0
    center: bool = True
    pad_mode: str = "constant"
    mono_strategy: str = "ARITHMETIC_MEAN_FLOAT64"
    f0_algorithm: str = "LIBROSA_PYIN"
    energy_algorithm: str = "LIBROSA_RMS"
    n_thresholds: int = 100
    beta_parameters: tuple[float, float] = (2.0, 18.0)
    boltzmann_parameter: float = 2.0
    resolution: float = 0.1
    max_transition_rate: float = 35.92
    switch_prob: float = 0.01
    no_trough_prob: float = 0.01
    transition_min_prob: float = 0.0001

    def __post_init__(self):
        if type(self.frame_length) is not int or self.frame_length < 4 or self.frame_length % 2:
            raise ValueError("frame_length must be an even integer >= 4")
        if type(self.hop_length) is not int or not 0 < self.hop_length <= self.frame_length:
            raise ValueError("hop_length must be in [1, frame_length]")
        if type(self.center) is not bool or self.pad_mode != "constant":
            raise ValueError("Expected boolean center and constant-zero padding")
        if (self.mono_strategy != "ARITHMETIC_MEAN_FLOAT64" or self.f0_algorithm != "LIBROSA_PYIN"
                or self.energy_algorithm != "LIBROSA_RMS"):
            raise ValueError("Unsupported algorithm or mono strategy")
        if type(self.beta_parameters) is not tuple or len(self.beta_parameters) != 2:
            raise ValueError("beta_parameters must be an immutable pair")
        numbers = (self.fmin_hz, self.fmax_hz, self.boltzmann_parameter, self.resolution,
                   self.max_transition_rate, self.switch_prob, self.no_trough_prob,
                   self.transition_min_prob, *self.beta_parameters)
        if any(type(value) not in (int, float) or not math.isfinite(value)
               or value <= 0 for value in numbers):
            raise ValueError("Parameters must be finite positive numbers")
        if not self.fmax_hz > self.fmin_hz:
            raise ValueError("fmax_hz must exceed fmin_hz")
        if any(value >= 1 for value in (self.resolution, self.switch_prob, self.no_trough_prob,
                                       self.transition_min_prob)):
            raise ValueError("Resolution and probability settings must be in (0, 1)")
        if type(self.n_thresholds) is not int or self.n_thresholds <= 0:
            raise ValueError("n_thresholds must be a positive integer")

    def to_dict(self):
        return {**asdict(self), "beta_parameters": list(self.beta_parameters),
                "unvoiced_f0_policy": "NULL_WHEN_UNVOICED",
                "rms_dtype": "float64", "sample_quantization": "FLOOR_START_CEIL_END_HALF_OPEN",
                "frame_selection": "ALIGNMENT_START_LE_CENTER_LT_END_EXACT_SAMPLE_RATIO",
                "derived_time_decimal_precision": 34, "quantile_method": "linear"}
