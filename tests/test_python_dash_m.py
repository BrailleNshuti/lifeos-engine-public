"""`python -m lifeos` works and gives the same answer as the `lifeos` command (found missing in the round 7 scan)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_python_dash_m_prints_the_version_and_exits_zero():
    done = subprocess.run([sys.executable, "-m", "lifeos", "--version"], capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert done.returncode == 0 and "lifeos" in (done.stdout + done.stderr).lower()


def test_python_dash_m_passes_the_exit_code_through(tmp_path):
    done = subprocess.run([sys.executable, "-m", "lifeos", "--home", str(tmp_path), "selfcheck"], capture_output=True, text=True,
                          cwd=ROOT, timeout=60)
    assert done.returncode == 2 and "now.md" in done.stderr  # not a data home: the same refusal the script gives
