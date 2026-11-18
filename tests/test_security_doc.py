"""Every promise in docs/SECURITY.md names a test that exists."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = (ROOT / "docs" / "SECURITY.md").read_text(encoding="utf-8")
REFS = re.findall(r"`(tests/[\w/]+\.py)::(test_\w+)`", DOC)


def test_the_doc_lists_promises():
    assert len(REFS) >= 10


def test_every_referenced_test_exists():
    for file, name in REFS:
        path = ROOT / file
        assert path.exists(), f"{file} is missing"
        names = {n.name for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(n, ast.FunctionDef)}
        assert name in names, f"{file} has no {name}"


def test_the_doc_states_its_limits():
    assert "## Not promised" in DOC and "tamper-evident, not tamper-proof" in DOC
