"""Cancellation lifecycle tests: real spawned workers, explicit synthetic analyzers."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import os
import subprocess
import sys
import time
import unittest
from test_product_api import client, wav
from speech_xray.product.config import Settings
from speech_xray.product.orchestrator import ProductOrchestrator
from speech_xray.product.prompts import PromptRegistry
from speech_xray.product.errors import ProductError
from product_test_support import FakeAnalyzer


class DescendantAnalyzer(FakeAnalyzer):
    def analyse(self, request):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
        (request.workspace / 'child.pid').write_text(str(child.pid))
        try:
            time.sleep(60)
        finally:
            child.terminate(); child.wait()


def wait_until(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate(): return
        time.sleep(0.02)
    raise AssertionError('Expected lifecycle milestone not reached')


class AnalysisCancellationTests(unittest.TestCase):
    def test_http_cancel_releases_capacity_and_workspace_and_is_idempotent(self):
        token = str(uuid4())
        with client(delay=60) as (c, app, settings), ThreadPoolExecutor() as pool:
            job = pool.submit(c.post, '/api/v1/analyses', data={'prompt_id':'learner-v1-001'},
                              files={'audio':('a.wav',wav(),'audio/wav')}, headers={'X-Analysis-Token':token})
            wait_until(lambda: list(settings.workspace_root.glob('*/private-marker.txt')))
            result = c.post('/api/v1/analyses/cancel/'+token).json()
            self.assertIn(result['status'], ('CANCELLED', 'CANCELLING'))
            response = job.result(timeout=15)
            self.assertEqual(response.status_code,409)
            self.assertEqual(response.json()['error_code'],'ANALYSIS_CANCELLED')
            self.assertEqual(list(settings.workspace_root.iterdir()),[])
            self.assertEqual(c.post('/api/v1/analyses/cancel/'+token).json()['status'],'CANCELLED')
            self.assertTrue(app.state.service.slots.acquire(blocking=False))
            app.state.service.slots.release()
            app.state.service.analyzer.delay=0
            self.assertEqual(c.post('/api/v1/analyses',data={'prompt_id':'learner-v1-002'},files={'audio':('a.wav',wav(),'audio/wav')},headers={'X-Analysis-Token':str(uuid4())}).status_code,200)

    def test_wrong_token_cannot_cancel_another_analysis(self):
        with client(delay=60) as (c, app, s), ThreadPoolExecutor() as pool:
            token=str(uuid4())
            job=pool.submit(c.post,'/api/v1/analyses',data={'prompt_id':'learner-v1-001'},files={'audio':('a.wav',wav(),'audio/wav')},headers={'X-Analysis-Token':token})
            wait_until(lambda: token in app.state.service.controls)
            self.assertEqual(c.post('/api/v1/analyses/cancel/'+str(uuid4())).json()['status'],'NOT_FOUND')
            self.assertFalse(app.state.service.controls[token].requested.is_set())
            c.post('/api/v1/analyses/cancel/'+token)
            self.assertEqual(job.result(timeout=15).json()['error_code'],'ANALYSIS_CANCELLED')

    def test_cancel_before_worker_start_and_finished_result_wins_late_cancel(self):
        with TemporaryDirectory() as folder:
            settings=Settings(workspace_root=Path(folder)/'requests')
            service=ProductOrchestrator(settings,PromptRegistry(settings.prompt_registry,settings.binding_registry),FakeAnalyzer(settings))
            token=str(uuid4())
            with self.assertRaises(ProductError) as raised:
                with service.session('learner-v1-001',control_token=token) as request:
                    self.assertEqual(service.cancel(token,wait_seconds=0),'CANCELLING')
                    service.analyse(request)
            self.assertEqual(raised.exception.code,'ANALYSIS_CANCELLED')
            self.assertEqual(service.cancel(token),'CANCELLED')
        with client() as (c,app,s):
            token=str(uuid4())
            response=c.post('/api/v1/analyses',data={'prompt_id':'learner-v1-001'},files={'audio':('a.wav',wav(),'audio/wav')},headers={'X-Analysis-Token':token})
            self.assertEqual(response.status_code,200)
            self.assertEqual(c.post('/api/v1/analyses/cancel/'+token).json()['status'],'FINISHED')
            self.assertFalse(app.state.service.controls[token].requested.is_set())

    def test_cancel_stops_worker_descendant_process(self):
        with TemporaryDirectory() as folder, ThreadPoolExecutor() as pool:
            s=Settings(workspace_root=Path(folder)/'requests')
            service=ProductOrchestrator(s,PromptRegistry(s.prompt_registry,s.binding_registry),DescendantAnalyzer(s))
            token=str(uuid4())
            def run():
                with service.session('learner-v1-001',control_token=token) as request:
                    return service.analyse(request)
            job=pool.submit(run)
            wait_until(lambda: list(s.workspace_root.glob('*/child.pid')))
            child_pid=int(next(s.workspace_root.glob('*/child.pid')).read_text())
            service.cancel(token)
            with self.assertRaises(ProductError): job.result(timeout=15)
            self.assertEqual(service.cancel(token),'CANCELLED')
            if os.name == 'nt':
                listing=subprocess.check_output(['tasklist','/FI',f'PID eq {child_pid}','/FO','CSV','/NH'],text=True)
                self.assertNotIn(f'"{child_pid}"',listing)
            else:
                # A terminated descendant can briefly be an OS zombie, but cannot execute.
                stat=Path(f'/proc/{child_pid}/stat')
                self.assertTrue(not stat.exists() or stat.read_text().split()[2]=='Z')
            self.assertEqual(list(s.workspace_root.iterdir()),[])

    def test_token_validation_reuse_and_cors(self):
        with client() as (c,app,s):
            self.assertEqual(c.post('/api/v1/analyses',data={'prompt_id':'learner-v1-001'},files={'audio':('a.wav',wav(),'audio/wav')},headers={'X-Analysis-Token':'bad-token'}).status_code,422)
            token=str(uuid4())
            args={'data':{'prompt_id':'learner-v1-001'},'files':{'audio':('a.wav',wav(),'audio/wav')},'headers':{'X-Analysis-Token':token}}
            self.assertEqual(c.post('/api/v1/analyses',**args).status_code,200)
            self.assertEqual(c.post('/api/v1/analyses',**args).json()['details']['reason_code'],'CONTROL_TOKEN_REUSED')
            self.assertEqual(c.post('/api/v1/analyses/cancel/not-a-uuid').status_code,422)
            preflight=c.options('/api/v1/analyses',headers={'Origin':'http://localhost:3000','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'x-analysis-token'})
            self.assertEqual(preflight.status_code,200)


if __name__ == '__main__': unittest.main()
