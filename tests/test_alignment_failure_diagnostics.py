"""Operational diagnostics survive request cleanup without retaining audio."""
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

from speech_xray.product.config import Settings
from speech_xray.product.diagnostics import retain_alignment_failure, MAX_LOGS, MAX_TAIL_BYTES, MAX_REPORTS
from speech_xray.product.errors import ProductError
from speech_xray.product.runtime import MFARuntime, no_alignments_reported


class AlignmentFailureDiagnosticsTests(unittest.TestCase):
    def setup_case(self, root):
        settings = Settings(workspace_root=root/'requests')
        request = settings.workspace_root/'request-workspace'
        request.mkdir(parents=True)
        audio = request/'input.wav'
        with wave.open(str(audio), 'wb') as writer:
            writer.setnchannels(1); writer.setsampwidth(2); writer.setframerate(48000)
            writer.writeframes(b'PCM_CONTENT_DO_NOT_RETAIN' * 2)
        folder = request/'primary'
        folder.mkdir()
        return settings, folder, audio

    def test_receipt_survives_cleanup_and_retains_no_audio(self):
        with TemporaryDirectory() as tmp:
            settings, folder, audio = self.setup_case(Path(tmp))
            (folder/'alignment.log').write_text('KaldiProcessingError: input feature extraction failed')
            report = retain_alignment_failure(settings, folder, audio, returncode=1)
            shutil.rmtree(folder.parent)
            content = report.read_text(encoding='utf-8')
            receipt = json.loads(content)
            self.assertEqual(receipt['audio_metadata']['sample_rate_hz'], 48000)
            self.assertIn('KaldiProcessingError', receipt['logs'][0]['tail'])
            self.assertNotIn('PCM_CONTENT_DO_NOT_RETAIN', content)
            self.assertEqual(list(report.parent.iterdir()), [report])

    def test_log_count_tail_and_history_are_bounded(self):
        with TemporaryDirectory() as tmp:
            settings, folder, audio = self.setup_case(Path(tmp))
            (folder/'alignment.log').write_bytes(b'x' * (MAX_TAIL_BYTES*2) + b'end')
            logs = folder/'mfa-temp'; logs.mkdir()
            for i in range(MAX_LOGS*2): (logs/f'{i:03}.log').write_text('detail')
            for _ in range(MAX_REPORTS+3):
                report = retain_alignment_failure(settings, folder, audio, returncode=1)
            receipt = json.loads(report.read_text(encoding='utf-8'))
            self.assertEqual(len(receipt['logs']), MAX_LOGS)
            self.assertEqual(len(receipt['logs'][0]['tail']), MAX_TAIL_BYTES)
            self.assertTrue(receipt['logs'][0]['tail'].endswith('end'))
            self.assertEqual(len(list(report.parent.glob('*.json'))), MAX_REPORTS)

    def test_diagnostic_write_failure_does_not_mask_execution_error(self):
        with TemporaryDirectory() as tmp:
            settings, folder, audio = self.setup_case(Path(tmp))
            with patch('pathlib.Path.write_text', side_effect=OSError('disk full')):
                self.assertIsNone(retain_alignment_failure(settings, folder, audio, returncode=1))

    def run_failed_runtime(self, message, returncode=7):
        with TemporaryDirectory() as tmp:
            settings, folder, audio = self.setup_case(Path(tmp))
            folder.rmdir()
            runtime = MFARuntime.__new__(MFARuntime)
            runtime.settings = settings.model_copy(update={
                name: SimpleNamespace(path=Path(tmp)/'unused')
                for name in ('acoustic_model', 'dictionary', 'g2p_model')})
            binding = SimpleNamespace(prompt=SimpleNamespace(display_text='Authored test text'))
            def fail(argv, **kwargs):
                kwargs['stdout'].write(message.encode('utf-8'))
                return SimpleNamespace(returncode=returncode)
            with patch('speech_xray.product.runtime.verify'), patch('speech_xray.product.runtime.subprocess.run', side_effect=fail):
                try:
                    result = runtime.align(audio, binding, folder)
                    error = None
                except ProductError as caught:
                    error, result = caught, None
            report = next((Path(tmp)/'alignment-failures').glob('*.json'))
            receipt = json.loads(report.read_text(encoding='utf-8'))
            return result, error, receipt

    def test_runtime_failure_keeps_original_code_and_diagnostic(self):
        _, error, receipt = self.run_failed_runtime('EXPLICIT_ENGINE_FAILURE')
        self.assertEqual(error.code, 'ALIGNMENT_RUNTIME_UNAVAILABLE')
        self.assertEqual(error.reason, 'MFA_EXECUTION_FAILED')
        self.assertEqual(receipt['returncode'], 7)
        self.assertEqual(receipt['logs'][0]['tail'], 'EXPLICIT_ENGINE_FAILURE')

    def test_no_alignment_is_unusable_evidence_not_runtime_unavailable(self):
        result, error, receipt = self.run_failed_runtime(
            'Traceback (most recent call last):\n'
            '  File "alignment/mixins.py", line 315, in align_utterances\n'
            '    raise NoAlignmentsError(self.num_current_utterances, self.beam, self.retry_beam)\n'
            'montreal_forced_aligner.exceptions.NoAlignmentsError: NoAlignmentsError:\n\n'
            'There were no successful alignments for 1 utterances.\n', 1)
        self.assertIsNone(result)
        self.assertIsNone(error)
        self.assertEqual(receipt['returncode'], 1)

    def test_permission_error_mentioning_no_alignment_is_still_operational(self):
        _, error, _ = self.run_failed_runtime(
            '  raise NoAlignmentsError\nPermissionError: Cannot create file\n', 1)
        self.assertEqual(error.reason, 'MFA_EXECUTION_FAILED')

    def test_absent_failure_log_never_inferred_as_no_alignment(self):
        with TemporaryDirectory() as tmp:
            self.assertFalse(no_alignments_reported(Path(tmp)/'missing.log'))


if __name__ == '__main__': unittest.main()
