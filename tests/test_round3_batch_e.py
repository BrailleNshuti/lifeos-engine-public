"""Round 3 items 17 and 28: `ask --failover` uses the delegate chain, and docs/COMMANDS.md is generated from the parser."""
import shutil
from pathlib import Path

import pytest

from lifeos import ask, commandsdoc
from lifeos.cli import build_parser, main

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def home(tmp_path, demo, monkeypatch):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    monkeypatch.setenv("LIFEOS_HOME", str(target))
    for name in ("claude", "codex", "gemini", "grok", "qwen", "ollama"):
        monkeypatch.setitem(ask.ADAPTERS, name, lambda prompt, name=name: f"ANSWER FROM {name} https://example.org 2026-11-27 next step")
    return target


def test_without_failover_a_failing_seat_stops_the_call(home, monkeypatch, capsys):
    def slow(prompt):
        raise ask.AskError("codex timed out after 600 s.")

    monkeypatch.setitem(ask.ADAPTERS, "codex", slow)
    assert main(["ask", "codex", "T-261116"]) == 3
    assert "ANSWER FROM claude" not in capsys.readouterr().out


def test_with_failover_the_next_seat_answers_and_says_so(home, monkeypatch, capsys):
    def slow(prompt):
        raise ask.AskError("codex timed out after 600 s.")

    monkeypatch.setitem(ask.ADAPTERS, "codex", slow)
    assert main(["ask", "codex", "T-261116", "--failover"]) == 0
    out = capsys.readouterr().out
    assert "ANSWER FROM claude" in out and "fell back" in out


def test_failover_still_never_sends_a_private_task_to_the_cloud(home, monkeypatch, capsys):
    task = next((home / "tasks").glob("T-261116*.md"))
    task.write_text(task.read_text(encoding="utf-8").replace("Ship the context command", "Sort my bank csv privately"), encoding="utf-8")
    cloud = []
    for name in ("claude", "codex", "gemini", "grok"):
        monkeypatch.setitem(ask.ADAPTERS, name, lambda prompt, name=name: cloud.append(name) or "cloud")

    def down(prompt):
        raise ask.AskError("qwen timed out")

    monkeypatch.setitem(ask.ADAPTERS, "qwen", down)
    monkeypatch.setitem(ask.ADAPTERS, "ollama", down)
    main(["ask", "codex", "T-261116", "--failover"])
    assert set(cloud) <= {"codex"}  # the explicit first seat may be asked; no other cloud seat may be


def test_failover_dry_run_sends_nothing(home, capsys):
    assert main(["ask", "codex", "T-261116", "--failover", "--dry-run"]) == 0
    assert "dry run" in capsys.readouterr().out


# 28. docs/COMMANDS.md
def test_the_generated_page_lists_every_command_with_its_help():
    page = commandsdoc.render(build_parser())
    for name in ("ask", "delegate", "sunday", "egress", "unrate", "verify-quotes", "dash-export", "help-me"):
        assert f"`lifeos {name}`" in page
    assert page.startswith("# Commands")


def test_the_page_is_deterministic():
    assert commandsdoc.render(build_parser()) == commandsdoc.render(build_parser())


def test_the_checked_in_page_is_not_stale():
    path = ROOT / "docs" / "COMMANDS.md"
    assert path.exists(), "run: lifeos commands --out docs/COMMANDS.md"
    assert path.read_text(encoding="utf-8").replace("\r\n", "\n") == commandsdoc.render(build_parser()), "stale: lifeos commands --out docs/COMMANDS.md"


def test_the_command_writes_the_page(tmp_path, capsys):
    out = tmp_path / "C.md"
    assert main(["commands", "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("# Commands")
