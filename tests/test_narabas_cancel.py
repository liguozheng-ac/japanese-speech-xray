"""Persistent inference cancellation retains workspace/slot until owned work returns."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from product_test_support import FakeAnalyzer
from test_product_api import wav
from speech_xray.product.config import Settings
from speech_xray.product.errors import ProductError
from speech_xray.product.orchestrator import ProductOrchestrator, report_stage
from speech_xray.product.prompts import PromptRegistry


class BlockingPersistentAnalyzer(FakeAnalyzer):
    persistent_execution = True
    stage_labels = ('音频准备', '音素对齐', '目标结构检查', '声学证据与参考计算', '结果整理')

    def __init__(self, settings):
        super().__init__(settings)
        self.started, self.finish = threading.Event(), threading.Event()

    def analyse(self, request):
        report_stage(request, 2)
        self.started.set()
        if not self.finish.wait(5): raise RuntimeError('test inference was not released')
        return super().analyse(request)


class PersistentCancellationTests(unittest.TestCase):
    def test_cancel_discards_late_result_and_releases_workspace_only_after_return(self):
        with TemporaryDirectory() as folder, ThreadPoolExecutor() as pool:
            settings = Settings(workspace_root=Path(folder)/'requests')
            analyzer = BlockingPersistentAnalyzer(settings)
            service = ProductOrchestrator(settings, PromptRegistry(settings.prompt_registry,
                                           settings.binding_registry), analyzer)
            def run(token):
                with service.session('learner-v1-001', control_token=token) as request:
                    request.audio_path.write_bytes(wav())
                    return service.analyse(request)
            job = pool.submit(run, 'cancelled-turn')
            self.assertTrue(analyzer.started.wait(3))
            self.assertEqual(service.progress('cancelled-turn')['stage_label'], '音素对齐')
            self.assertEqual(service.cancel('cancelled-turn', wait_seconds=0), 'CANCELLING')
            self.assertTrue(list(settings.workspace_root.iterdir()))
            with self.assertRaisesRegex(ProductError, 'SERVICE_BUSY'):
                with service.session('learner-v1-002'): pass
            analyzer.finish.set()
            with self.assertRaises(ProductError) as raised: job.result(timeout=5)
            self.assertEqual(raised.exception.code, 'ANALYSIS_CANCELLED')
            self.assertEqual(service.cancel('cancelled-turn'), 'CANCELLED')
            self.assertEqual(service.progress('cancelled-turn')['state'], 'CANCELLED')
            self.assertEqual(list(settings.workspace_root.iterdir()), [])
            self.assertEqual(service.last_metrics, {})
            result = run('next-turn')
            self.assertEqual(result.status, 'COMPLETED')
            self.assertEqual(service.cancel('next-turn'), 'FINISHED')


if __name__ == '__main__': unittest.main()
