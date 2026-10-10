"""Exercise the shared fixtures in a checkout without local runtime artifacts."""

from pathlib import Path
import os
import shutil
import subprocess
import sys


def test_fresh_checkout_initializes_pytest_temp_directory(tmp_path):
    checkout = tmp_path / "checkout"
    project = checkout / "ReverieCli-py"
    tests = project / "tests"
    tests.mkdir(parents=True)
    shutil.copyfile(Path(__file__).with_name("conftest.py"), tests / "conftest.py")
    (tests / "test_smoke.py").write_text(
        "from pathlib import Path\n"
        "import os\n"
        "def test_isolated_paths(tmp_path, tmp_path_factory):\n"
        "    checkout = Path(__file__).resolve().parents[2]\n"
        "    assert tmp_path_factory.getbasetemp().parent == checkout / '.runtime'\n"
        "    assert tmp_path.is_dir()\n"
        "    assert Path(os.environ['REVERIE_APP_ROOT']).is_relative_to(checkout / 'dist')\n",
        encoding="utf-8",
    )
    assert not (checkout / ".runtime").exists()
    env = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    env.pop("PYTEST_ADDOPTS", None)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_smoke.py"],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
