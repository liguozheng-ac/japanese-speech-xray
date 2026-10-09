"""Associate existing spans with frame centers; never move or split alignment times."""

from fractions import Fraction
import numpy as np

from speech_xray.japanese.models import LongVowelSpan
from .models import (AcousticSpanEvidence, AcousticTrack, ExtractionStatus as Status,
                     MeasurementSummary, SampleInterval)
from .timing import center_in_span, quantize_interval, sample_time_ms, time_fraction_ms


def summarize(values) -> MeasurementSummary:
    array = np.asarray(tuple(values), dtype=np.float64)
    if not len(array):
        return MeasurementSummary()
    if not np.isfinite(array).all():
        raise ValueError("Non-finite summary input")
    q25, median, q75 = np.quantile(array, [0.25, 0.5, 0.75], method="linear")
    return MeasurementSummary(len(array), float(median), float(np.min(array)), float(np.max(array)),
                              float(q25), float(q75), float(q75 - q25))


def unavailable_span(span: LongVowelSpan, status: Status, audio_hash=None, warning=""):
    return AcousticSpanEvidence(span, audio_hash, None, (), 0, None,
                                MeasurementSummary(), MeasurementSummary(), status,
                                (warning,) if warning else ())


def span_evidence(track: AcousticTrack, span: LongVowelSpan, audio_sha256: str) -> AcousticSpanEvidence:
    start, end = time_fraction_ms(span.start_ms), time_fraction_ms(span.end_ms)
    if end < start:
        return unavailable_span(span, Status.INVALID_SPAN, audio_sha256, "Reversed alignment interval")
    if start < 0 or end > Fraction(track.audio_frame_count * 1000, track.sample_rate_hz):
        return unavailable_span(span, Status.SPAN_OUT_OF_AUDIO_RANGE, audio_sha256,
                                "Requested interval exceeds the original WAV domain; not clipped")
    first, last = quantize_interval(span.start_ms, span.end_ms, track.sample_rate_hz)
    interval = SampleInterval(first, last, sample_time_ms(first, track.sample_rate_hz),
                              sample_time_ms(last, track.sample_rate_hz))
    selected = tuple(frame for frame in track.frames
                     if center_in_span(frame.center_sample, track.sample_rate_hz, span.start_ms, span.end_ms))
    if not selected:
        status = track.extraction_status if not track.frames else Status.NO_FRAMES
        return AcousticSpanEvidence(span, audio_sha256, interval, (), 0, None,
                                    MeasurementSummary(), MeasurementSummary(), status, track.warnings)
    count = sum(frame.voiced is True for frame in selected)
    ratio = count / len(selected) if track.f0_status == Status.OK else None
    status = (Status.OK if count else Status.NO_VOICED_FRAMES
              ) if track.f0_status == Status.OK else track.f0_status
    observed_start = min(frame.observed_start_sample for frame in selected)
    observed_end = max(frame.observed_end_sample for frame in selected)
    observed = SampleInterval(observed_start, observed_end,
                              sample_time_ms(observed_start, track.sample_rate_hz),
                              sample_time_ms(observed_end, track.sample_rate_hz))
    return AcousticSpanEvidence(
        span, audio_sha256, interval, tuple(frame.index for frame in selected), count, ratio,
        summarize(frame.f0_hz for frame in selected if frame.voiced and frame.f0_hz is not None),
        summarize(frame.rms for frame in selected), status, track.warnings, observed)
