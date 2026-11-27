"""`lifeos unrate TASK [MODEL]` removes the last rating of a task (a mistake), and `rate` warns about a low score without a note."""
import csv
import shutil

import pytest

from lifeos import learn
from lifeos.cli import main

TEXT = "implement a python module"


@pytest.fixture
def home(tmp_path, demo, monkeypatch):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    monkeypatch.setenv("LIFEOS_HOME", str(target))
    return target


def rows(home):
    return list(csv.DictReader(open(home / "logs" / "ratings.csv", encoding="utf-8")))


def test_it_removes_only_the_last_rating_of_the_task(home):
    learn.add_rating(home, "T-1", "claude", 4, TEXT, note="first")
    learn.add_rating(home, "T-2", "codex", 3, TEXT, note="other task")
    learn.add_rating(home, "T-1", "claude", 1, TEXT, note="mistake")
    removed = learn.remove_last(home, "T-1")
    assert removed["note"] == "mistake"
    assert [r["note"] for r in rows(home)] == ["first", "other task"]


def test_a_model_narrows_the_choice(home):
    learn.add_rating(home, "T-1", "claude", 4, TEXT, note="c")
    learn.add_rating(home, "T-1", "codex", 2, TEXT, note="x")
    assert learn.remove_last(home, "T-1", "claude")["note"] == "c"
    assert [r["note"] for r in rows(home)] == ["x"]


def test_nothing_to_remove_gives_none_and_changes_nothing(home):
    learn.add_rating(home, "T-1", "claude", 4, TEXT, note="keep")
    before = (home / "logs" / "ratings.csv").read_bytes()
    assert learn.remove_last(home, "T-9") is None
    assert (home / "logs" / "ratings.csv").read_bytes() == before


def test_a_missing_file_gives_none(home):
    (home / "logs" / "ratings.csv").unlink(missing_ok=True)
    assert learn.remove_last(home, "T-1") is None


def test_notes_with_commas_and_quotes_survive_a_removal(home):
    learn.add_rating(home, "T-1", "claude", 4, TEXT, note='said "yes", then no')
    learn.add_rating(home, "T-2", "claude", 3, TEXT, note="gone")
    learn.remove_last(home, "T-2")
    assert rows(home)[0]["note"] == 'said "yes", then no'


def test_cli_unrate(home, capsys):
    learn.add_rating(home, "T-261116", "claude", 4, TEXT, note="oops")
    assert main(["unrate", "T-261116"]) == 0
    assert "removed" in capsys.readouterr().out and rows(home) == []
    assert main(["unrate", "T-261116"]) == 1
    assert "no rating" in capsys.readouterr().err.lower()


def test_a_low_score_without_a_note_is_warned_about(home, capsys):
    assert main(["rate", "T-261116", "claude", "2"]) == 0
    assert "note" in capsys.readouterr().err.lower()


def test_a_low_score_with_a_note_is_not_warned_about(home, capsys):
    assert main(["rate", "T-261116", "claude", "2", "--note", "missed the URL"]) == 0
    assert "add a note" not in capsys.readouterr().err.lower()


def test_a_high_score_without_a_note_is_fine(home, capsys):
    assert main(["rate", "T-261116", "claude", "5"]) == 0
    assert "add a note" not in capsys.readouterr().err.lower()
