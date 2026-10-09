"""Technical WAV intake reuses TASK-004 decoding, never judges pronunciation."""

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import soundfile as sf

from speech_xray.acoustics.audio import InvalidAudioError, load_audio


def inspect_audio(path):
    path=Path(path)
    try:
        raw=path.read_bytes()
    except OSError:
        return None,None,"MISSING_OR_UNREADABLE_AUDIO"
    digest=sha256(raw).hexdigest()
    if not raw:
        return None,digest,"AUDIO_EMPTY"
    try:
        data=load_audio(path)
    except InvalidAudioError:
        try:
            info=sf.info(BytesIO(raw))
            reason="AUDIO_EMPTY" if info.frames==0 else "UNREADABLE_OR_UNSUPPORTED_AUDIO"
        except (sf.LibsndfileError,OSError,ValueError):
            reason="UNREADABLE_AUDIO"
        return None,digest,reason
    metadata=data.metadata
    if metadata.sha256!=digest:
        return None,digest,"AUDIO_CHANGED_DURING_VALIDATION"
    reason=None
    if metadata.sample_rate_hz<16000:
        reason="SAMPLE_RATE_BELOW_INTAKE_MINIMUM"
    elif metadata.subtype not in {"PCM_16","PCM_24"}:
        reason="NONCANONICAL_PCM_ENCODING"
    elif metadata.original_peak_abs_amplitude==0:
        reason="DIGITAL_SILENCE"
    elif metadata.analysis_peak_abs_amplitude==0:
        reason="MONO_ANALYSIS_DIGITAL_SILENCE"
    return metadata,digest,reason
