"""T9 and T10: the dashboard export survives awkward ratings and never carries a task body."""
import json
import shutil

import pytest

from lifeos import dashdata, learn


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def load(out, name):
    return json.loads((out / name).read_text(encoding="utf-8"))


def test_a_note_with_commas_quotes_and_non_ascii_text_survives_the_export(home, tmp_path):
    note = 'said "yes", then “no”, plus Straße, über, 日本語; and a tab\there'
    learn.add_rating(home, "T-261116", "claude", 4, "implement a python module", note=note)
    out = tmp_path / "out"
    dashdata.export(home, out, commands=56)
    last = load(out, "ratings.json")[-1]
    assert last["model"] == "claude" and "Straße" in last["note"] and "日本語" in last["note"]
    assert "\t" not in last["note"] and "\n" not in last["note"]


def test_a_missing_ratings_file_gives_an_empty_list(home, tmp_path):
    ratings = home / "logs" / "ratings.csv"
    if ratings.exists():
        ratings.unlink()
    out = tmp_path / "out"
    dashdata.export(home, out, commands=56)
    assert load(out, "ratings.json") == []


def test_a_broken_waiting_file_gives_an_empty_list(home, tmp_path):
    (home / "waiting.json").write_text("{not json", encoding="utf-8")
    out = tmp_path / "out"
    dashdata.export(home, out, commands=56)
    assert load(out, "waiting.json") == []


def test_a_waiting_file_that_is_not_a_list_gives_an_empty_list(home, tmp_path):
    (home / "waiting.json").write_text(json.dumps({"item": "x"}), encoding="utf-8")
    out = tmp_path / "out"
    dashdata.export(home, out, commands=56)
    assert load(out, "waiting.json") == []


def test_a_task_row_carries_only_id_status_due_and_a_short_goal_never_the_body(home, tmp_path):
    long_goal = "Goal " + "word " * 60
    body_secret = "BODY-SECRET-DO-NOT-EXPORT"
    task = home / "tasks" / "T-261201-edge.md"
    task.write_text(f"---\nid: T-261201-edge\ngoal: {long_goal}\ndone_when: x\nroute: me\nlevel: L1\nstatus: inbox\ndue: 2026-12-01\n---\n"
                    f"## Task\n{body_secret}\n", encoding="utf-8")
    out = tmp_path / "out"
    dashdata.export(home, out, commands=56)
    raw = (out / "tasks.json").read_text(encoding="utf-8")
    assert body_secret not in raw
    row = next(r for r in load(out, "tasks.json") if r["id"] == "T-261201-edge")
    assert set(row) == {"id", "status", "due", "title"}
    assert len(row["title"]) <= dashdata.TITLE_MAX and row["due"] == "2026-12-01"


def test_export_creates_the_folder_and_overwrites_old_files(home, tmp_path):
    out = tmp_path / "deep" / "er" / "out"
    dashdata.export(home, out, commands=56)
    (out / "runs.json").write_text("stale", encoding="utf-8")
    dashdata.export(home, out, commands=56)
    assert isinstance(load(out, "runs.json"), list)
