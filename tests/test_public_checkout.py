"""Public resource isolation and real learner extraction with no reference bundle."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import numpy as np
from fastapi.testclient import TestClient
from reference_test_support import ROOT
from test_prosody import wav
from speech_xray.api.app import create_app
from speech_xray.product.config import Settings, load_settings

class PublicCheckoutTests(unittest.TestCase):
    def test_explicit_mfa_default_has_no_implicit_private_config(self):
        with patch.dict('os.environ', {'SPEECH_XRAY_CONFIG':'', 'SPEECH_XRAY_ALIGNER':''}):
            self.assertEqual(load_settings().alignment_engine, 'mfa')
        # Source publication must not introduce implicit private runtime resources.
        self.assertTrue((ROOT / 'frontend/src/WorkspaceEmpty.tsx').is_file())
        self.assertFalse((ROOT / 'frontend/public/local-backgrounds/58-desktop.mp4').exists())
        self.assertEqual(list((ROOT / 'frontend/public/audio/reference').glob('*.wav')), [])

    def test_real_tone_extracts_with_reference_missing_and_alignment_unready(self):
        with TemporaryDirectory() as folder:
            settings = Settings(workspace_root=Path(folder))
            with patch.dict('os.environ', {'SPEECH_XRAY_REFERENCE_AUDIO_DIR':str(Path(folder)/'absent')}):
                with TestClient(create_app(settings)) as client:
                    self.assertEqual(client.get('/api/v1/health/ready').status_code, 503)
                    reply = client.post('/api/prosody/v1/curves', data={'prompt_id':'learner-v1-001'},
                                        files={'audio':('engineering.wav',wav(.2 * np.sin(2 * np.pi * 220 * np.arange(32000) / 16000)))})
                    self.assertEqual(reply.status_code, 200, reply.text)
                    self.assertEqual(reply.json()['learner']['status'], 'AVAILABLE')
                    self.assertIsNone(reply.json()['reference'])
                    self.assertEqual(reply.json()['reference_reason'], 'SYNTHETIC_REFERENCE_UNAVAILABLE')
            self.assertEqual(list(Path(folder).iterdir()), [])

if __name__ == '__main__': unittest.main()
