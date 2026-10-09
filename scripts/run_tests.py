"""Run public engineering tests and print an explicit machine-readable receipt."""
from pathlib import Path
import json
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'services/speech-api/src'), str(ROOT / 'tests')]

if __name__ == '__main__':
    started = time.perf_counter()
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern='test_*.py')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    receipt = dict(total=result.testsRun, passed=result.testsRun-len(result.errors)-len(result.failures)-len(result.skipped),
                   failed=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
                   skipped_tests=[dict(test=str(t), reason=r) for t,r in result.skipped],
                   duration_seconds=round(time.perf_counter()-started, 3))
    print('PUBLIC_TEST_RECEIPT=' + json.dumps(receipt, ensure_ascii=False))
    sys.exit(0 if result.wasSuccessful() else 1)
