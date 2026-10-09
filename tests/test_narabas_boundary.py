import hashlib
from decimal import Decimal
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/speech-api/src"))
from speech_xray.product.native_boundary import BoundaryUnusable, validate_native_segments
from speech_xray.product.narabas_audio import alignment_copy


class NativeBoundaryTests(unittest.TestCase):
    def validate(self, segments, sequence=("m","a","a","t"), duration=Decimal(1000)):
        return validate_native_segments(segments,sequence,duration,(1,2),(0,1,2,3))

    def test_each_native_long_vowel_pair_is_preserved(self):
        for vowel in "aiu":
            raw = [[0,.1,"m"],[.1,.14,vowel],[.14,.22,vowel],[.22,.3,"t"]]
            result = self.validate(raw,("m",vowel,vowel,"t"))
            self.assertEqual((result[1][0],result[2][1]),(Decimal(100),Decimal(220)))
            self.assertEqual(len(result),4)
            self.assertEqual(result[1][1],Decimal(140))

    def test_missing_and_incomplete_sequences_rejected(self):
        for raw in ([],[[0,.1,"m"],[.1,.2,"a"],[.2,.3,"t"]]):
            with self.assertRaisesRegex(BoundaryUnusable,"INCOMPLETE_PHONE_SEQUENCE"):
                self.validate(raw)

    def test_illegal_native_intervals_fail_closed(self):
        mutations = [(0,.1,"m"),(.1,.2,"a"),(.2,.3,"a"),(.3,.4,"t")]
        for interval, reason in [((.1,.1,"a"),"NONPOSITIVE"),((.05,.2,"a"),"NONMONOTONIC"),
                                ((.1,2,"a"),"OUTSIDE"),((float('nan'),.2,"a"),"NONFINITE")]:
            raw = list(mutations)
            raw[1] = interval
            with self.assertRaisesRegex(BoundaryUnusable,reason):
                self.validate(raw)

    def test_pair_must_be_adjacent_same_native_vowels(self):
        raw = [[0,.1,"m"],[.1,.2,"a"],[.21,.3,"a"],[.3,.4,"t"]]
        with self.assertRaisesRegex(BoundaryUnusable,"PAIR_MISMATCH"):
            self.validate(raw)

    def test_malformed_worker_output_has_explicit_boundary_reason(self):
        for raw in (None, [[0, .1]], [[0, .1, None]]):
            with self.assertRaisesRegex(BoundaryUnusable, 'MALFORMED_NATIVE_SEGMENT'):
                self.validate(raw)
        with self.assertRaisesRegex(BoundaryUnusable, 'MALFORMED_NATIVE_TIMESTAMP'):
            self.validate([[0,.1,'m'],['unknown',.2,'a'],[.2,.3,'a'],[.3,.4,'t']])

    def test_conversion_preserves_original_and_absolute_time_origin(self):
        import numpy as np
        for rate in (8000,16000,24000,44100,48000):
            with tempfile.TemporaryDirectory() as folder:
                original, derived = Path(folder)/"original.wav",Path(folder)/"derived.wav"
                pcm = np.zeros(rate,dtype="<i2")
                pcm[rate//2] = 16000
                with wave.open(str(original),"wb") as writer:
                    writer.setparams((1,2,rate,0,"NONE","not compressed"))
                    writer.writeframes(pcm.tobytes())
                before = hashlib.sha256(original.read_bytes()).hexdigest()
                receipt = alignment_copy(original,derived)
                with wave.open(str(derived),"rb") as reader:
                    self.assertEqual((reader.getnchannels(),reader.getsampwidth(),reader.getframerate(),reader.getnframes()),(1,2,16000,16000))
                    peak = int(np.argmax(np.frombuffer(reader.readframes(16000),dtype="<i2")))
                self.assertLessEqual(abs(peak-8000),1)
                self.assertEqual(receipt["origin_shift_samples"],0)
                self.assertEqual(before,hashlib.sha256(original.read_bytes()).hexdigest())

    def test_stereo_never_silently_converted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"stereo.wav"
            with wave.open(str(path),"wb") as writer:
                writer.setparams((2,2,16000,0,"NONE","not compressed"))
                writer.writeframes(struct.pack('<hh',100,100)*160)
            with self.assertRaisesRegex(ValueError,"NO_CHANNEL_CONVERSION"):
                alignment_copy(path,Path(folder)/"mono.wav")


if __name__ == "__main__":
    unittest.main()
