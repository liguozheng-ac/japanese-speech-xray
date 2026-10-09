"""Live IPC progress, independent GET transport and terminal cleanup."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import time
import unittest
from fastapi.testclient import TestClient
from product_test_support import FakeAnalyzer
from speech_xray.api.app import create_app
from speech_xray.product.config import Settings
from speech_xray.product.errors import ProductError
from speech_xray.product.orchestrator import ProductOrchestrator, report_stage
from speech_xray.product.prompts import PromptRegistry
from test_product_api import wav

class StageAnalyzer(FakeAnalyzer):
    def analyse(self, request):
        for index in range(2,6):
            report_stage(request,index); time.sleep(.3)
            if self.mode=='stage_error' and index==3:
                raise ProductError('INTERNAL_PIPELINE_ERROR','PIPELINE','STAGE_TEST_ERROR')
        return super().analyse(request)

class AnalysisProgressTests(unittest.TestCase):
    def exercise(self,mode='available',cancel=False):
        with TemporaryDirectory() as directory:
            settings=Settings(workspace_root=Path(directory)/'requests')
            app=create_app(settings,StageAnalyzer(settings,mode))
            with TestClient(app) as c, ThreadPoolExecutor() as pool:
                key=str(uuid4())
                job=pool.submit(c.post,'/api/v1/analyses',data={'prompt_id':'learner-v1-001'},files={'audio':('a.wav',wav(),'audio/wav')},headers={'X-Analysis-Token':key})
                seen=[]; deadline=time.monotonic()+15
                while not job.done() and time.monotonic()<deadline:
                    progress=c.get('/api/v1/analyses/progress/'+key).json()
                    if progress['state']!='NOT_FOUND':
                        seen.append((progress,not job.done()))
                        if cancel and progress['stage_index']==2: c.post('/api/v1/analyses/cancel/'+key)
                    time.sleep(.03)
                response=job.result(timeout=5)
                final=c.get('/api/v1/analyses/progress/'+key).json()
                self.assertEqual(list(settings.workspace_root.iterdir()),[])
                self.assertTrue(app.state.service.slots.acquire(blocking=False)); app.state.service.slots.release()
                return response,seen,final
    def test_pending_post_live_stages_and_same_correlation(self):
        response,seen,final=self.exercise()
        self.assertEqual(response.status_code,200); self.assertEqual(final['state'],'FINISHED')
        self.assertEqual(final['request_id'],response.json()['analysis_id'])
        self.assertEqual(final['request_id'],response.headers['X-Request-ID'])
        self.assertEqual([x['stage_index'] for x in final['history']],[1,2,3,4,5])
        self.assertTrue(all(any(p['stage_index']==i and pending for p,pending in seen) for i in (2,3,4)))
        self.assertNotIn('audio',final); self.assertNotIn('targets',final)
    def test_error_retains_last_stage(self):
        response,seen,final=self.exercise('stage_error')
        self.assertEqual(response.status_code,500); self.assertEqual(final['state'],'ERROR'); self.assertEqual(final['stage_index'],3)
    def test_cancel_terminal_cleanup(self):
        response,seen,final=self.exercise(cancel=True)
        self.assertEqual(response.status_code,409); self.assertEqual(final['state'],'CANCELLED'); self.assertEqual(final['stage_index'],2)
    def test_bounded_registry_and_no_backwards_stage(self):
        with TemporaryDirectory() as directory:
            settings=Settings(workspace_root=Path(directory)/'requests')
            service=ProductOrchestrator(settings,PromptRegistry(settings.prompt_registry,settings.binding_registry),FakeAnalyzer(settings))
            for i in range(140):
                with service.session('learner-v1-001',control_token=str(uuid4())) as request:
                    service.update_progress(request.control_token,3); service.update_progress(request.control_token,2)
                    self.assertEqual(service.progress(request.control_token)['stage_index'],3)
            self.assertEqual(len(service.controls),128); self.assertEqual(service.progress(str(uuid4())),{'state':'NOT_FOUND'})
    def test_unknown_and_invalid_key(self):
        with TestClient(create_app(Settings(),FakeAnalyzer(Settings()))) as c:
            self.assertEqual(c.get('/api/v1/analyses/progress/'+str(uuid4())).json(),{'state':'NOT_FOUND'})
            self.assertEqual(c.get('/api/v1/analyses/progress/not-a-uuid').status_code,422)
