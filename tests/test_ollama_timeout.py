"""T3: the local-model wait is the value call_timeout gives, it reaches the local HTTP call, and the error names it."""
import json

import pytest

from lifeos import ask


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body


@pytest.fixture(autouse=True)
def loopback(monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("LIFEOS_TIMEOUT", raising=False)


def test_the_default_local_wait_is_the_local_timeout(monkeypatch):
    seen = {}

    def fake_open(req, timeout):
        seen["timeout"] = timeout
        return FakeResponse(json.dumps({"response": "ok"}).encode())

    monkeypatch.setattr(ask, "_open_local", fake_open)
    assert ask.ollama_generate("hi", "llama3.2") == "ok"
    assert seen["timeout"] == ask.call_timeout("ollama") == ask.LOCAL_TIMEOUT


def test_the_environment_overrides_the_local_wait(monkeypatch):
    monkeypatch.setenv("LIFEOS_TIMEOUT", "900")
    seen = {}

    def fake_open(req, timeout):
        seen["timeout"] = timeout
        return FakeResponse(json.dumps({"response": "ok"}).encode())

    monkeypatch.setattr(ask, "_open_local", fake_open)
    ask.ollama_generate("hi", "llama3.2")
    assert seen["timeout"] == 900


def test_a_timeout_names_the_wait_and_suggests_another_seat(monkeypatch):
    def slow(req, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr(ask, "_open_local", slow)
    with pytest.raises(ask.AskError) as raised:
        ask.ollama_generate("hi", "llama3.2")
    message = str(raised.value)
    assert f"{ask.LOCAL_TIMEOUT} s" in message and "another seat" in message


def test_the_timeout_message_follows_the_environment(monkeypatch):
    monkeypatch.setenv("LIFEOS_TIMEOUT", "77")

    def slow(req, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr(ask, "_open_local", slow)
    with pytest.raises(ask.AskError, match="77 s"):
        ask.ollama_generate("hi", "qwen3.5:4b")


@pytest.mark.parametrize("name,expected", [("qwen", ask.LOCAL_TIMEOUT), ("ollama", ask.LOCAL_TIMEOUT),
                                           ("claude", ask.TIMEOUT), ("codex", ask.TIMEOUT), ("gemini", ask.TIMEOUT),
                                           ("grok", ask.TIMEOUT)])
def test_every_seat_has_the_right_default_wait(name, expected):
    assert ask.call_timeout(name) == expected


@pytest.mark.parametrize("raw", ["0", "3601", "-5", "abc", "", "1.5", "²"])
def test_a_bad_environment_value_keeps_the_default(monkeypatch, raw):
    monkeypatch.setenv("LIFEOS_TIMEOUT", raw)
    assert ask.call_timeout("qwen") == ask.LOCAL_TIMEOUT
    assert ask.call_timeout("codex") == ask.TIMEOUT
