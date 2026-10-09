"""Real pYIN engineering signals and independent HTTP behavior, not human accuracy."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import threading
import unittest
import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient
from reference_test_support import ROOT
from speech_xray.api.app import create_app
from speech_xray.product.config import Settings
from speech_xray.product.errors import ProductError
from speech_xray.product.audio import validate_audio
from speech_xray.prosody.extract import decode_wav, extract


def wav(samples=None, rate=16000, channels=1, subtype='PCM_16'):
    samples = np.zeros(rate) if samples is None else samples
    if channels == 2:
        samples = np.column_stack((samples, samples))
    stream = BytesIO(); sf.write(stream, samples, rate, format='WAV', subtype=subtype)
    return stream.getvalue()


class ProsodyExtraction(unittest.TestCase):
    def test_real_pyin_tone_silence_tone_gaps_and_original_clock(self):
        rate = 48000
        t = np.arange(rate) / rate
        tone = .25 * np.sin(2 * np.pi * 220 * t)
        raw = wav(np.concatenate((tone, np.zeros(rate), tone)), rate)
        row = extract(raw, Settings())
        self.assertEqual(row['status'], 'AVAILABLE')
        self.assertEqual(row['audio_sha256'], sha256(raw).hexdigest())
        self.assertEqual(row['sample_rate_hz'], rate)
        self.assertEqual(row['sample_count'], rate * 3)
        self.assertEqual(row['parameters']['resampling'], 'NONE')
        self.assertAlmostEqual(row['observations']['median_f0_hz'], 220, delta=3)
        for i, f in enumerate(row['frames']):
            self.assertAlmostEqual(f['time_ms'], i * row['parameters']['hop_length'] / rate * 1000)
            self.assertLess(f['time_ms'], row['duration_ms'])
            self.assertTrue(0 <= f['voiced_probability'] <= 1)
            if 1250 < f['time_ms'] < 1750:
                self.assertFalse(f['voiced']); self.assertIsNone(f['f0_hz'])
        self.assertTrue(any(f['voiced'] for f in row['frames'] if f['time_ms'] > 2200))

    def test_silence_and_too_short_abstain(self):
        for samples, reason in [(np.zeros(16000), 'LOW_ENERGY_NO_F0'), (np.ones(200) * .1, 'AUDIO_TOO_SHORT_FOR_F0')]:
            row = extract(wav(samples), Settings())
            self.assertEqual(row['status'], 'ABSTAINED'); self.assertEqual(row['reason'], reason)
            self.assertIsNone(row['observations']); self.assertTrue(all(f['f0_hz'] is None for f in row['frames']))

    def test_pyin_failure_preserves_energy_and_abstains(self):
        t = np.arange(16000) / 16000
        with patch('librosa.pyin', side_effect=RuntimeError('TEST_INITIALIZATION_FAILURE')):
            row = extract(wav(.2 * np.sin(2 * np.pi * 220 * t)), Settings())
        self.assertEqual(row['status'], 'ABSTAINED'); self.assertEqual(row['reason'], 'F0_EXTRACTION_FAILED')
        self.assertIsNone(row['observations']); self.assertTrue(row['frames'])
        self.assertTrue(all(f['f0_hz'] is None and np.isfinite(f['rms_dbfs']) for f in row['frames']))

    def test_weak_voiced_estimates_are_not_drawn_but_evidence_survives(self):
        t=np.arange(16000)/16000
        def weak(samples, **kwargs):
            count=1+len(samples)//kwargs['hop_length']
            return np.full(count,220.),np.ones(count,dtype=bool),np.full(count,.01)
        with patch('librosa.pyin',side_effect=weak):
            row=extract(wav(.2*np.sin(2*np.pi*220*t)),Settings())
        self.assertEqual(row['status'],'ABSTAINED')
        self.assertTrue(all(f['f0_hz'] is None and f['pyin_voiced'] and f['voiced_probability']==.01 for f in row['frames']))

    def test_admission_matches_existing_upload_domain_without_channel_conversion(self):
        cases = [wav(), wav(rate=8000), wav(rate=48000), wav(channels=2), wav(subtype='FLOAT'), wav(rate=7999), wav(rate=48001), b'invalid', wav(np.zeros(16000 * 31))]
        with TemporaryDirectory() as folder:
            path = Path(folder)/'original.wav'
            for raw in cases:
                path.write_bytes(raw)
                results = []
                for fn in [lambda: validate_audio(path, Settings()), lambda: decode_wav(raw, Settings())]:
                    try: fn(); results.append('ADMITTED')
                    except ProductError as e: results.append(e.code)
                self.assertEqual(results[0], results[1])
                self.assertEqual(path.read_bytes(), raw)

    def test_three_same_sentence_haruka_resources_real_extraction(self):
        self.skipTest("Private Haruka audio excluded; no redistribution permission established")


class ProsodyHTTP(unittest.TestCase):
    def test_runs_with_alignment_unavailable_and_no_learner_disk_retention(self):
        self.skipTest("Private Haruka audio excluded; no redistribution permission established")

    def test_busy_is_bounded_and_capacity_releases_after_failure(self):
        entered, finish = threading.Event(), threading.Event()
        def waiting(*args):
            entered.set(); finish.wait(5); raise ProductError('INVALID_AUDIO', 'INPUT_VALIDATED', 'TEST_FAILURE')
        with TemporaryDirectory() as folder, TestClient(create_app(Settings(workspace_root=Path(folder)))) as c:
            replies=[]
            with patch('speech_xray.prosody.routes.extract', side_effect=waiting):
                worker=threading.Thread(target=lambda: replies.append(c.post('/api/prosody/v1/curves', data={'prompt_id':'learner-v1-001'}, files={'audio':('a.wav',wav())})))
                worker.start(); self.assertTrue(entered.wait(3))
                busy=c.post('/api/prosody/v1/curves', data={'prompt_id':'learner-v1-001'},files={'audio':('a.wav',wav())})
                self.assertEqual(busy.status_code,503); self.assertEqual(busy.json()['reason'],'PROSODY_BUSY')
                finish.set(); worker.join(6); self.assertFalse(worker.is_alive())
            self.assertEqual(replies[0].status_code,422)
            retry=c.post('/api/prosody/v1/curves', data={'prompt_id':'learner-v1-001'},files={'audio':('a.wav',wav())})
            self.assertEqual(retry.status_code,200); self.assertEqual(retry.json()['learner']['status'],'ABSTAINED')

    def test_reference_hash_failure_does_not_lose_learner_curve(self):
        self.skipTest("Private Haruka audio excluded; no redistribution permission established")

    def test_bad_audio_unknown_prompt_duplicate_fields_and_limits(self):
        with TemporaryDirectory() as folder, TestClient(create_app(Settings(workspace_root=Path(folder),max_upload_bytes=100000))) as c:
            cases=[({'prompt_id':'unknown'},wav(),404),({'prompt_id':'learner-v1-001'},b'broken',422),({'prompt_id':'learner-v1-001'},wav(channels=2),422),({'prompt_id':'learner-v1-001','extra':'x'},wav(),422),({'prompt_id':'learner-v1-001'},b'x'*100001,413)]
            for fields,raw,status in cases:
                reply=c.post('/api/prosody/v1/curves',data=fields,files={'audio':('a.wav',raw)})
                self.assertEqual(reply.status_code,status,reply.text)
            duplicate=c.post('/api/prosody/v1/curves',data={'prompt_id':'learner-v1-001'},files=[('audio',('a.wav',wav())),('audio',('b.wav',wav()))])
            self.assertEqual(duplicate.status_code,422)


if __name__ == '__main__': unittest.main()
