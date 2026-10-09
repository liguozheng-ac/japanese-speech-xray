"""Only sample-rate conversion; original bytes and the time origin are preserved."""
import math
from pathlib import Path
import wave

RESAMPLE_METHOD = "SCIPY_RESAMPLE_POLY_PCM16_1.0.0"


def alignment_copy(original, derived):
    import numpy as np
    from scipy.signal import resample_poly
    with wave.open(str(original), "rb") as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2 or source.getcomptype() != "NONE":
            raise ValueError("MONO_PCM16_REQUIRED_NO_CHANNEL_CONVERSION")
        rate, count = source.getframerate(), source.getnframes()
        if not 8000 <= rate <= 48000 or count <= 0:
            raise ValueError("INVALID_ORIGINAL_AUDIO_DOMAIN")
        pcm = np.frombuffer(source.readframes(count), dtype="<i2")
    gcd = math.gcd(rate, 16000)
    converted = pcm if rate == 16000 else resample_poly(pcm.astype(np.float64), 16000//gcd, rate//gcd)
    converted = np.clip(np.rint(converted), -32768, 32767).astype("<i2")
    # resample_poly's ceil count represents the same origin; excess is < one output sample.
    if len(converted) != (count*16000+rate-1)//rate:
        raise ValueError("DERIVED_AUDIO_TIME_AXIS_MISMATCH")
    Path(derived).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(derived), "wb") as result:
        result.setnchannels(1)
        result.setsampwidth(2)
        result.setframerate(16000)
        result.writeframes(converted.tobytes())
    return {"method": RESAMPLE_METHOD, "original_rate_hz": rate, "original_frames": count,
            "alignment_rate_hz": 16000, "alignment_frames": len(converted), "origin_shift_samples": 0}
