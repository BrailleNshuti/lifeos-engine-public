"""`lifeos sunday`: the numbers for the weekly review in one page (no model call, nothing written)."""
import datetime as dt
import json
import shutil

import pytest

from lifeos import sunday
from lifeos.cli import main

TODAY = dt.date(2026, 11, 29)


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def add_runs(home, records):
    with (home / "logs" / "runs.jsonl").open("a", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def test_the_page_has_every_section(home):
    text = sunday.build(home, today=TODAY)
    for heading in ("Did each part earn its place", "Seat speed", "Ratings this week", "Stale", "Open mistakes", "Next"):
        assert heading in text, heading


def test_ratings_of_the_last_seven_days_only(home):
    (home / "logs" / "ratings.csv").write_text(
        "date,task,model,score,kind,note\n2026-11-28,T-1,claude,4,code,good\n2026-11-20,T-2,codex,2,code,old\n", encoding="utf-8")
    text = sunday.build(home, today=TODAY)
    assert "claude" in text.split("Ratings this week", 1)[1].split("Stale", 1)[0]
    assert "old" not in text.split("Ratings this week", 1)[1].split("Stale", 1)[0]


def test_no_ratings_this_week_says_so(home):
    (home / "logs" / "ratings.csv").write_text("date,task,model,score,kind,note\n", encoding="utf-8")
    assert "No ratings this week" in sunday.build(home, today=TODAY)


def test_it_writes_nothing(home):
    before = {p: p.read_bytes() for p in home.rglob("*") if p.is_file() and p.suffix != ".lock"}  # the advisory lock file is not data
    sunday.build(home, today=TODAY)
    after = {p: p.read_bytes() for p in home.rglob("*") if p.is_file() and p.suffix != ".lock"}
    assert before == after


def test_a_home_with_no_logs_does_not_crash(tmp_path):
    (tmp_path / "now.md").write_text("# Now\n", encoding="utf-8")
    assert "Sunday review" in sunday.build(tmp_path, today=TODAY)


def test_the_cli_prints_the_page(home, capsys, monkeypatch):
    monkeypatch.setenv("LIFEOS_HOME", str(home))
    assert main(["sunday"]) == 0
    assert "Sunday review" in capsys.readouterr().out
