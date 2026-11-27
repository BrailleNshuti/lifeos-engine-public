"""Failure injection for every cloud seat adapter (no real CLI is ever started): a missing tool, a failing exit, a hang,
a usage limit, empty or garbage output. Each must end in a short, redacted, correctly classified error."""
import subprocess

import pytest

from lifeos import ask, seats

CLOUD = ["claude", "codex", "gemini", "grok"]
KEY = "ghp_" + "a1B2" * 9  # assembled at run time, never a real token


class Done:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def install(monkeypatch, result=None, raises=None, exe="/fake/bin/tool"):
    monkeypatch.setattr(ask.shutil, "which", lambda name: exe)

    def fake_run(*args, **kwargs):
        if raises is not None:
            raise raises
        return result

    monkeypatch.setattr(ask.subprocess, "run", fake_run)


@pytest.mark.parametrize("seat", CLOUD)
def test_a_missing_tool_is_reported_as_missing(seat, monkeypatch):
    monkeypatch.setattr(ask.shutil, "which", lambda name: None)
    with pytest.raises(ask.ToolMissing) as raised:
        ask.ADAPTERS[seat]("hello")
    assert "not installed" in str(raised.value) and seats.failure_kind(str(raised.value)) == "missing"


@pytest.mark.parametrize("seat", CLOUD)
def test_a_hang_becomes_a_timeout_error(seat, monkeypatch):
    install(monkeypatch, raises=subprocess.TimeoutExpired(cmd="x", timeout=5))
    with pytest.raises(ask.AskError) as raised:
        ask.ADAPTERS[seat]("hello")
    assert "timed out" in str(raised.value) and seats.failure_kind(str(raised.value)) == "timeout"


@pytest.mark.parametrize("seat", CLOUD)
def test_a_usage_limit_is_classified_and_rests_the_seat(seat, monkeypatch):
    install(monkeypatch, result=Done(1, "", "You've hit your usage limit. Try again at 4:02 PM"))
    with pytest.raises(ask.AskError) as raised:
        ask.ADAPTERS[seat]("hello")
    assert seats.failure_kind(str(raised.value)) == "usage_limit"


@pytest.mark.parametrize("seat", CLOUD)
def test_a_failing_exit_hides_a_secret_in_stderr_and_stays_short(seat, monkeypatch):
    noisy = f"fatal: token {KEY} rejected\n" + "stack line\n" * 400
    install(monkeypatch, result=Done(2, "", noisy))
    with pytest.raises(ask.AskError) as raised:
        ask.ADAPTERS[seat]("hello")
    message = str(raised.value)
    assert KEY not in message
    assert len(message) < 600, len(message)


@pytest.mark.parametrize("seat", ["gemini", "grok"])
@pytest.mark.parametrize("garbage", ["", "not json at all", "{\"unexpected\": 1}", "\x00\x01\x02", "[1, 2, 3]"])
def test_garbage_or_empty_output_is_an_error_not_an_answer(seat, garbage, monkeypatch):
    install(monkeypatch, result=Done(0, garbage, ""))
    with pytest.raises(ask.AskError):
        ask.ADAPTERS[seat]("hello")


@pytest.mark.parametrize("seat", ["claude", "codex"])
def test_plain_text_seats_return_the_text_trimmed(seat, monkeypatch):
    install(monkeypatch, result=Done(0, "  an answer \n\n", ""))
    assert ask.ADAPTERS[seat]("hello") == "an answer"


@pytest.mark.parametrize("seat", ["claude", "codex"])
def test_an_empty_answer_from_a_plain_text_seat_reaches_the_free_check_as_empty(seat, monkeypatch):
    from lifeos.check import check_answer
    install(monkeypatch, result=Done(0, "", ""))
    text = ask.ADAPTERS[seat]("hello")
    assert text == "" and "empty answer" in check_answer(text)
