"""Round 3 items 12 and 18: what is sent to each cloud seat is the pack and nothing else, and never travels in argv."""
import shutil

import pytest

from lifeos import ask

SECRET_FREE_PROMPT = "UNIQUE PROMPT BODY 90210 about a harmless task"
CLOUD = ["claude", "codex", "gemini", "grok"]


class Done:
    returncode, stdout, stderr = 0, "", ""


def capture(monkeypatch, stdout="ok answer"):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"], seen["kwargs"] = list(argv), kwargs
        done = Done()
        done.stdout = stdout
        return done

    monkeypatch.setattr(ask.shutil, "which", lambda name: "/fake/" + name)
    monkeypatch.setattr(ask.subprocess, "run", fake_run)
    return seen


@pytest.mark.parametrize("seat", ["claude", "codex"])
def test_the_prompt_travels_on_stdin_and_never_in_the_argument_list(seat, monkeypatch):
    seen = capture(monkeypatch)
    ask.ADAPTERS[seat](SECRET_FREE_PROMPT)
    assert seen["kwargs"]["input"] == SECRET_FREE_PROMPT
    assert not any(SECRET_FREE_PROMPT in part or "90210" in part for part in seen["argv"])


def test_gemini_sends_the_prompt_on_stdin_inside_the_event_and_not_in_argv(monkeypatch):
    stream = '{"event":"result","result":{"status":"SUCCESS","response":"fine"}}'
    seen = capture(monkeypatch, stdout=stream)
    ask.ADAPTERS["gemini"](SECRET_FREE_PROMPT)
    assert SECRET_FREE_PROMPT in seen["kwargs"]["input"]
    assert not any("90210" in part for part in seen["argv"])


def test_grok_sends_the_prompt_through_a_file_that_is_gone_afterwards(monkeypatch):
    import os
    paths = []

    def fake_cli(cmd, prompt, **kwargs):
        path = cmd[cmd.index("--prompt-file") + 1]
        paths.append(path)
        assert open(path, encoding="utf-8").read().endswith(SECRET_FREE_PROMPT)
        assert not any("90210" in part for part in cmd)
        return '{"text": "an answer"}'

    monkeypatch.setattr(ask, "_run_cli", fake_cli)
    ask.ADAPTERS["grok"](SECRET_FREE_PROMPT)
    assert paths and not os.path.exists(paths[0])


@pytest.mark.parametrize("seat", CLOUD)
def test_every_cloud_call_runs_in_an_empty_folder_not_the_project(seat, monkeypatch):
    stream = '{"event":"result","result":{"status":"SUCCESS","response":"fine"}}'
    seen = capture(monkeypatch, stdout=stream if seat == "gemini" else '{"text": "x"}' if seat == "grok" else "x")
    ask.ADAPTERS[seat]("hello")
    import tempfile
    cwd = str(seen["kwargs"].get("cwd") or "")
    assert cwd.startswith(tempfile.gettempdir()), cwd  # a fresh empty temp folder, never the repository or the home


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    (target / "me.md").write_text("# Me\nPRIVATE-ME-MARKER-3141\n", encoding="utf-8")
    (target / "now.md").write_text("# Now\nPRIVATE-NOW-MARKER-2718\n", encoding="utf-8")
    return target


@pytest.mark.parametrize("seat", CLOUD)
def test_a_cloud_seat_never_gets_me_or_now_unless_full_is_given(seat, home):
    sent = []
    adapters = {seat: lambda prompt: sent.append(prompt) or "answer https://example.org 2026-11-27 next step"}
    try:
        ask.run_ask(home, seat, "T-261116", adapters=adapters)
    except ask.Blocked:
        pytest.skip("this seat is not allowed the pack at all")
    assert sent and "PRIVATE-ME-MARKER-3141" not in sent[0] and "PRIVATE-NOW-MARKER-2718" not in sent[0]
