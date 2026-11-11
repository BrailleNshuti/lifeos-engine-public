import shutil

import pytest

from lifeos import check, delegate, mcp

GOOD = ("Added the export function. Evidence: pytest -q gave 12 passed; see lifeos/export.py:40. "
        "Open issue: none known. Next step: review the diff.")


def test_a_good_answer_has_no_flags():
    assert check.check_answer(GOOD) == []


@pytest.mark.parametrize("text,word", [
    ("", "empty"),
    ("ok", "short"),
    ("I'm sorry, I can't access your files, so I cannot do this. Next step: paste them.", "could not"),
    ("Use only the context given. Answer with the result only: what was done.", "prompt"),
    ("All done, everything is fixed and works. Next step: nothing.", "evidence"),
    ("Source: https://example.com/page says it is fine. Evidence 3 items. Next step: none.", "date"),
    ("It probably works and should be fine, I assume. 3 files. Next step: none.", "guess"),
    ("Fixed in lifeos/a.py with 4 tests passing. Open issues: none.", "next step"),
])
def test_each_problem_is_flagged(text, word):
    assert any(word in f for f in check.check_answer(text)), check.check_answer(text)


def test_flags_are_short_and_cost_no_model_call():
    flags = check.check_answer("done")
    assert flags and all(len(f) < 90 for f in flags)


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def test_delegate_returns_flags_for_a_weak_answer(home):
    adapters = {"claude": lambda p: "All done and fixed.", "codex": lambda p: GOOD}
    weak = delegate.run_delegate(home, "T-261116", model="claude", adapters=adapters)
    assert weak["flags"]
    good = delegate.run_delegate(home, "T-261116", model="codex", adapters=adapters)
    assert good["flags"] == []


def test_mcp_text_shows_the_warning(home, monkeypatch):
    monkeypatch.setattr(delegate, "ADAPTERS", {"codex": lambda p: "All done and fixed.", "claude": lambda p: "x"})
    reply = mcp.handle(home, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                              "params": {"name": "lifeos_delegate", "arguments": {"task": "T-261116"}}})
    assert "CHECK" in reply["result"]["content"][0]["text"]


def test_mcp_text_has_no_warning_for_a_good_answer(home, monkeypatch):
    monkeypatch.setattr(delegate, "ADAPTERS", {"codex": lambda p: GOOD, "claude": lambda p: "x"})
    reply = mcp.handle(home, {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                              "params": {"name": "lifeos_delegate", "arguments": {"task": "T-261116"}}})
    assert "CHECK" not in reply["result"]["content"][0]["text"]


@pytest.mark.parametrize("text,model", [
    ("Implement the export function", "claude"),
    ("Refactor the parser module in lifeos/parse.py", "claude"),
    ("Run pytest and review the diff for bugs", "codex"),
])
def test_claude_writes_code_codex_checks_it(text, model):
    assert delegate.pick(text)[0] == model
