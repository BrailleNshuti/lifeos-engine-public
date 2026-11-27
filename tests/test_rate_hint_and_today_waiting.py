"""Two small things for daily use: `lifeos rate` says what the router now thinks, and `lifeos today` shows the waiting list."""
import datetime as dt
import json
import shutil

import pytest

from lifeos import learn, today
from lifeos.cli import main

TODAY = dt.date(2026, 11, 27)


@pytest.fixture
def home(tmp_path, demo, monkeypatch):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    monkeypatch.setenv("LIFEOS_HOME", str(target))
    return target


def test_rate_prints_what_the_router_thinks(home, capsys):
    assert main(["rate", "T-261116", "claude", "4"]) == 0
    out = capsys.readouterr().out
    assert "rated claude 4/5" in out and "router:" in out and "default" in out


def test_rate_names_a_better_seat_once_the_evidence_is_clear(home, capsys):
    text = "implement a python module"
    for model, score in (("claude", 2), ("claude", 2), ("claude", 2), ("codex", 5), ("codex", 5), ("codex", 5)):
        learn.add_rating(home, "T-261116", model, score, text, today=TODAY)
    capsys.readouterr()
    assert main(["rate", "T-261116", "claude", "2"]) == 0
    assert "codex" in capsys.readouterr().out.split("router:", 1)[1]


def test_today_lists_the_waiting_items(home):
    (home / "waiting.json").write_text(json.dumps([
        {"item": "Install the RAM", "who": "you", "when": "2026-11-27"},
        {"item": "Decide about the bot", "who": "you", "when": "anytime"}]), encoding="utf-8")
    view = today.build(home, today=TODAY)
    assert [w["item"] for w in view["waiting"]] == ["Install the RAM", "Decide about the bot"]
    text = today.render(view)
    assert "Waiting" in text and "Install the RAM" in text


def test_today_without_a_waiting_file_has_no_waiting_section(home):
    view = today.build(home, today=TODAY)
    assert view["waiting"] == []
    assert "Waiting" not in today.render(view)


def test_a_broken_waiting_file_does_not_break_today(home):
    (home / "waiting.json").write_text("{nope", encoding="utf-8")
    assert today.build(home, today=TODAY)["waiting"] == []


def test_only_the_first_five_waiting_items_are_shown(home):
    (home / "waiting.json").write_text(json.dumps([{"item": f"item {i}", "who": "you", "when": "soon"} for i in range(9)]), encoding="utf-8")
    text = today.render(today.build(home, today=TODAY))
    assert "item 4" in text and "item 5" not in text and "4 more" in text
