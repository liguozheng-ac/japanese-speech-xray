import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"services/speech-api/src"))
from speech_xray.product.narabas_runtime import NarabasRuntime, NarabasSpec, sha256

FAKE_WORKER = '''import sys,json,os,time,subprocess
print(json.dumps({'type':'ready','pid':os.getpid(),'sample_rate_hz':16000,'hop_length':320,'model_load_ms':1}),flush=True)
for line in sys.stdin:
 r=json.loads(line)
 if r.get('operation')=='shutdown': break
 p=r['audio_path']
 if p=='crash': sys.exit(9)
 if p=='timeout': time.sleep(5)
 if p.startswith('child-timeout:'):
  child = subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])
  with open(p.split(':',1)[1], 'a') as f: f.write(str(child.pid)+'\\n')
  time.sleep(5)
 if p=='noisy': sys.stderr.write('diagnostic-only '*5000); sys.stderr.flush()
 if p=='fail':
  print(json.dumps({'id':r['id'],'type':'error','error_class':'ValueError','error_message':'declared failure'}),flush=True)
 else:
  print(json.dumps({'id':r['id'],'type':'result','segments':[[0,.1,'a']],'alignment_ms':1}),flush=True)
'''


class NarabasRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        (root/"docs").mkdir()
        self.lock = root/"docs/lock.json"
        self.lock.write_text(json.dumps({'files':{},'python_base':'.'}))
        self.worker = root/"worker.py"
        self.worker.write_text(FAKE_WORKER)
        self.spec = NarabasSpec(Path(sys.executable),root,root/"model",self.lock,sha256(self.lock),root/"private",.5)
        real_popen = subprocess.Popen
        def popen(args, **kwargs):
            if any(str(arg).endswith('narabas_worker.py') for arg in args):
                return real_popen([sys.executable,"-u",str(self.worker)],**kwargs)
            return real_popen(args, **kwargs)
        self.patch_verify = patch.object(NarabasRuntime,"_verify")
        self.patch_process = patch("speech_xray.product.narabas_runtime.subprocess.Popen",side_effect=popen)
        self.patch_verify.start()
        self.patch_process.start()
        self.runtime = NarabasRuntime(self.spec)

    def tearDown(self):
        self.runtime.close()
        self.patch_process.stop()
        self.patch_verify.stop()
        self.folder.cleanup()

    def test_model_process_is_reused_and_shutdown_cleans_it(self):
        self.assertEqual(self.runtime.state,"STOPPED")
        self.runtime.align("success",["a"])
        pid = self.runtime.process.pid
        self.assertEqual(self.runtime.state,"READY")
        self.runtime.align("success",["a"])
        self.assertEqual(pid,self.runtime.process.pid)
        process = self.runtime.process
        self.runtime.close()
        self.assertEqual(self.runtime.state,"STOPPED")
        self.assertIsNotNone(process.poll())

    def test_declared_alignment_error_does_not_restart_model(self):
        with self.assertRaisesRegex(ValueError,"NARABAS_ALIGNMENT_ERROR"):
            self.runtime.align("fail",["a"])
        self.assertEqual(self.runtime.restarts,0)
        self.assertEqual(self.runtime.state,"READY")
        self.runtime.align("success",["a"])

    def test_crash_has_only_one_controlled_restart(self):
        with self.assertRaisesRegex(RuntimeError,"WORKER_EXITED"):
            self.runtime.align("crash",["a"])
        self.assertEqual(self.runtime.restarts,1)
        self.assertEqual(self.runtime.state,"ERROR")
        self.assertIsNone(self.runtime.process)
        with self.assertRaisesRegex(RuntimeError, 'RECOVERY_EXHAUSTED'):
            self.runtime.align('success', ['a'])
        self.assertIsNone(self.runtime.process)

    def test_worker_stderr_is_bounded_even_for_long_running_model(self):
        self.runtime.align('noisy', ['a'])
        self.runtime.close()
        logged = (self.spec.private_root/'worker-stderr.log').read_text(encoding='utf-8')
        self.assertGreater(len(logged), 0)
        self.assertLessEqual(len(logged), 16384)

    def test_timeout_kills_only_owned_worker_and_is_bounded(self):
        with self.assertRaisesRegex(TimeoutError,"WORKER_TIMEOUT"):
            self.runtime.align("timeout",["a"])
        self.assertEqual(self.runtime.restarts,1)
        self.assertIsNone(self.runtime.process)
        self.assertEqual(self.runtime.state,"ERROR")

    def test_changed_lock_is_rejected_before_launch(self):
        self.patch_verify.stop()
        self.spec.model.write_bytes(b'wrong model')
        with self.assertRaisesRegex(ValueError,"RESOURCE_HASH_MISMATCH"):
            NarabasRuntime(self.spec)
        self.patch_verify.start()

    @unittest.skipUnless(sys.platform == 'win32', 'Windows launcher/process-tree regression')
    def test_timeout_kills_owned_launcher_descendants(self):
        path = self.spec.private_root.parent/'descendants.txt'
        started = time.monotonic()
        with self.assertRaisesRegex(TimeoutError, 'WORKER_TIMEOUT'):
            self.runtime.align('child-timeout:'+str(path), ['a'])
        self.assertLess(time.monotonic()-started, 10)
        pids = path.read_text().splitlines()
        self.assertEqual(len(pids), 2)
        for pid in pids:
            listing = subprocess.check_output(['tasklist','/FI',f'PID eq {pid}','/FO','CSV','/NH'], text=True)
            self.assertNotIn(f'"{pid}"', listing)


if __name__ == "__main__":
    unittest.main()
