"""Engineering resource admission, preserving the original WAV bytes."""
from speech_xray.acoustics.audio import load_audio, InvalidAudioError
from .errors import ProductError


def validate_audio(path, settings):
    if path.stat().st_size > settings.max_upload_bytes:
        raise ProductError('UPLOAD_TOO_LARGE', 'INPUT_VALIDATED', 'UPLOAD_LIMIT')
    with path.open('rb') as stream:
        header = stream.read(12)
    if len(header) < 12:
        raise ProductError('INVALID_AUDIO', 'INPUT_VALIDATED', 'INVALID_HEADER')
    if header[:4] != b'RIFF' or header[8:12] != b'WAVE':
        raise ProductError('UNSUPPORTED_FORMAT', 'INPUT_VALIDATED', 'WAV_REQUIRED')
    # Inspect before full decode so a hostile header cannot request unbounded allocation.
    import soundfile as sf
    try:
        info = sf.info(path)
    except (OSError, ValueError, sf.LibsndfileError) as error:
        raise ProductError('INVALID_AUDIO', 'INPUT_VALIDATED', 'DECODE_FAILED') from error
    if info.format != 'WAV' or info.subtype != 'PCM_16' or info.channels != 1:
        raise ProductError('UNSUPPORTED_FORMAT', 'INPUT_VALIDATED', 'MONO_PCM16_REQUIRED')
    if info.frames <= 0 or not 8000 <= info.samplerate <= 48000:
        raise ProductError('INVALID_AUDIO', 'INPUT_VALIDATED', 'INVALID_AUDIO_DOMAIN')
    if info.frames * 1000 > settings.max_duration_ms * info.samplerate:
        raise ProductError('AUDIO_TOO_LONG', 'INPUT_VALIDATED', 'DURATION_LIMIT')
    try:
        return load_audio(path).metadata
    except InvalidAudioError as error:
        raise ProductError('INVALID_AUDIO', 'INPUT_VALIDATED', 'DECODE_FAILED') from error
