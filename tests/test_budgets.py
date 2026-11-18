"""Speed and size budgets: a regression here is a design smell, caught before it reaches a user."""
import contextlib
import io
import subprocess
import sys
import time
from pathlib import Path

import pytest

from lifeos.cli import main

ROOT = Path(__file__).resolve().parent.parent
FAST = [["week"], ["seats"], ["runs"], ["verify"], ["savings"], ["calibration"], ["task", "list"], ["decide", "list"]]


def test_importing_the_cli_stays_fast():
    start = time.perf_counter()
    subprocess.run([sys.executable, "-I", "-c", "import lifeos.cli"], check=True, cwd=ROOT)
    assert time.perf_counter() - start < 1.5  # about 0.1 s today; interpreter start included


@pytest.mark.parametrize("cmd", FAST, ids=lambda c: " ".join(c))
def test_everyday_commands_answer_quickly(cmd, demo):
    start = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        main(["--home", str(demo)] + cmd)
    assert time.perf_counter() - start < 2.0


def test_no_module_grows_past_the_size_ratchet():
    # One module per command and short files. The ceiling may be lowered, never raised without a reason in the PR.
    limits = {"cockpit.py": 1450, "cli.py": 1250, "ask.py": 1100}
    for path in (ROOT / "lifeos").glob("*.py"):
        n = len(path.read_text(encoding="utf-8").splitlines())
        assert n <= limits.get(path.name, 800), f"{path.name} has {n} lines"


def test_standard_library_only():
    import ast
    allowed = set(sys.stdlib_module_names) | {"lifeos"}
    for path in (ROOT / "lifeos").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) and node.level == 0 else [])
            for name in names:
                assert name.split(".")[0] in allowed, f"{path.name} imports {name}"
