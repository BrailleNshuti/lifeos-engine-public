"""A model answered but the result could not be saved (disk full, locked file): the answer must not be lost silently."""
import shutil

import pytest

from lifeos import ask
from lifeos.cli import main


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def full_disk(*args, **kwargs):
    raise OSError(28, "No space left on device")


def test_run_ask_raises_an_ask_error_that_carries_the_answer(home, monkeypatch):
    monkeypatch.setattr(ask, "record_result", full_disk)
    with pytest.raises(ask.AskError) as raised:
        ask.run_ask(home, "fake", "T-261116", adapters={"fake": lambda prompt: "THE REAL ANSWER"})
    assert raised.value.answer == "THE REAL ANSWER"
    assert "not saved" in str(raised.value).lower() and "No space left" in str(raised.value)


def test_the_cli_prints_the_answer_and_exits_3(home, monkeypatch, capsys):
    monkeypatch.setattr(ask, "record_result", full_disk)
    monkeypatch.setitem(ask.ADAPTERS, "grok", lambda prompt: "THE REAL ANSWER with a source https://example.org 2026-11-27")
    assert main(["--home", str(home), "ask", "grok", "T-261116"]) == 3
    seen = capsys.readouterr()
    assert "THE REAL ANSWER" in seen.out
    assert "not saved" in seen.err.lower()


def test_a_normal_answer_is_unchanged(home):
    path = ask.run_ask(home, "fake", "T-261116", adapters={"fake": lambda prompt: "FINE"})
    assert "FINE" in path.read_text(encoding="utf-8")


def test_a_blocked_or_failed_call_has_no_answer_attribute_value():
    assert ask.AskError("x").answer is None
