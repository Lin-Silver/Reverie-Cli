"""The optional Windows workflow must retain the scheduler's cross-process lock."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import time

import pytest


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows summary-lock compatibility')
def test_summary_lock_blocks_another_process_until_release(tmp_path):
    adapter_path = Path(__file__).resolve().parents[2] / 'scripts/verification/harness2_windows.py'
    spec = importlib.util.spec_from_file_location('harness2_windows', adapter_path)
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    previous = sys.modules.get('fcntl')
    adapter.install_summary_lock()
    lock = tmp_path / 'summary.lock'
    acquired = tmp_path / 'acquired'
    process = None
    try:
        import fcntl
        with lock.open('w') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            code = ('import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); '
                    'from harness2_windows import install_summary_lock; install_summary_lock(); '
                    'import fcntl; f=open(sys.argv[2],"w"); fcntl.flock(f,fcntl.LOCK_EX); '
                    'Path(sys.argv[3]).write_text("acquired"); fcntl.flock(f,fcntl.LOCK_UN)')
            process = subprocess.Popen([sys.executable, '-c', code, str(adapter_path.parent), str(lock), str(acquired)],
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            time.sleep(.3)
            assert process.poll() is None and not acquired.exists()
            fcntl.flock(handle, fcntl.LOCK_UN)
        assert process.wait(timeout=5) == 0
        assert acquired.read_text() == 'acquired'
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if previous is None:
            sys.modules.pop('fcntl', None)
        else:
            sys.modules['fcntl'] = previous
