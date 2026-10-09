"""WAV + mapped mora spans -> one reusable utterance track and span evidence."""

import importlib.metadata as metadata
from decimal import Decimal
from pathlib import Path
import platform

from speech_xray.japanese.models import MoraAnalysisResult
from .audio import InvalidAudioError, load_audio
from .config import AcousticConfig
from .models import AcousticEvidenceResult, ExtractionStatus as Status
from .mora_input import MoraSpanInput
from .span_evidence import span_evidence, unavailable_span
from .tracks import extract_track


def library_versions():
    return (("python", platform.python_version()),
            *((name, metadata.version(name)) for name in
              ("librosa", "numpy", "soundfile", "scipy", "numba", "llvmlite")))


def extract_acoustic_evidence(audio_path: str | Path, analysis: MoraAnalysisResult | MoraSpanInput,
                              config: AcousticConfig = AcousticConfig()) -> AcousticEvidenceResult:
    source = MoraSpanInput.from_analysis(analysis) if isinstance(analysis, MoraAnalysisResult) else analysis
    # Non-finite source timing cannot be retained in a finite JSON artifact.
    for span in source.long_vowel_spans:
        if any(not isinstance(value, Decimal) or not value.is_finite()
               for value in (span.start_ms, span.end_ms)):
            raise ValueError("Non-finite source span boundary")
    versions = library_versions()
    try:
        audio = load_audio(audio_path)
    except InvalidAudioError as error:
        return AcousticEvidenceResult(str(Path(audio_path).resolve()), source.source, source.sha256,
                                      source.alignment_source, None, config, versions, None,
                                      tuple(unavailable_span(span, Status.INVALID_AUDIO, warning=str(error))
                                            for span in source.long_vowel_spans), Status.INVALID_AUDIO, (str(error),))
    track = extract_track(audio, config)
    evidence = tuple(span_evidence(track, span, audio.metadata.sha256) for span in source.long_vowel_spans)
    messages = (*track.warnings, *(f"{item.original_span.id}: {item.extraction_status}"
                                  for item in evidence if item.extraction_status != Status.OK))
    overall_status = track.extraction_status
    if overall_status == Status.OK and any(item.extraction_status != Status.OK for item in evidence):
        overall_status = Status.PARTIAL_EVIDENCE
    return AcousticEvidenceResult(audio.metadata.source, source.source, source.sha256, source.alignment_source,
                                  audio.metadata, config, versions, track, evidence,
                                  overall_status, messages)
