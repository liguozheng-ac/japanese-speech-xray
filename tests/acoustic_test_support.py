"""Mathematical signals and authored linguistic objects; never speech synthesis."""

from decimal import Decimal
from pathlib import Path
import sys
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/speech-api/src"))
from speech_xray.alignment.models import AlignmentResult, PhoneInterval, WordInterval
from speech_xray.japanese.long_vowel_mapper import analyze_mora
from speech_xray.japanese.models import ReadingResult


def tone(rate=16000, size=8000, frequency=220.0, amplitude=0.2):
    return amplitude * np.sin(2 * np.pi * frequency * np.arange(size) / rate)


def write_wav(path, samples, rate=16000):
    sf.write(path, samples, rate, subtype="FLOAT")
    return Path(path)


def analysis(start="100", end="300", source="SELF_AUTHORED_ALIGNMENT"):
    left, right = Decimal(start), Decimal(end)
    class KnownReading:
        def reading_for(self, surface):
            return ReadingResult(surface, "コー", source="SELF_AUTHORED_TEST_READING")
    aligned = AlignmentResult(source, Decimal(0), max(right, Decimal(500)),
                              (WordInterval("コー", left, right),), (PhoneInterval("oː", left, right),))
    return analyze_mora(aligned, KnownReading())
