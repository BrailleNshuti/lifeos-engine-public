"""`lifeos dash-export`: the data files for a dashboard, from the home folder, in one command (no model call)."""
import json
import shutil

import pytest

from lifeos import dashdata
from lifeos.cli import main


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def test_the_export_writes_five_json_files(home, tmp_path):
    out = tmp_path / "out"
    written = dashdata.export(home, out, commands=56)
    assert sorted(p.name for p in written) == ["numbers.json", "ratings.json", "runs.json", "tasks.json", "waiting.json"]
    for path in written:
        assert isinstance(json.loads(path.read_text(encoding="utf-8")), list)


def test_numbers_are_label_value_rows_with_counts_only(home, tmp_path):
    out = tmp_path / "out"
    dashdata.export(home, out, commands=56)
    rows = json.loads((out / "numbers.json").read_text(encoding="utf-8"))
    labels = {r["metric"] for r in rows}
    assert {"Python modules", "Test functions", "Commands"} <= labels
    assert all(isinstance(r["value"], int) for r in rows)


def test_tasks_carry_id_status_due_and_title(home, tmp_path):
    out = tmp_path / "out"
    dashdata.export(home, out, commands=56)
    rows = json.loads((out / "tasks.json").read_text(encoding="utf-8"))
    assert rows and set(rows[0]) == {"id", "status", "due", "title"}


def test_ratings_rows_have_the_notes_trimmed_and_kind_left_out(home, tmp_path):
    from lifeos import learn
    learn.add_rating(home, "T-261116", "claude", 4, "implement a python module", note="clean diff")
    out = tmp_path / "out"
    dashdata.export(home, out, commands=56)
    rows = json.loads((out / "ratings.json").read_text(encoding="utf-8"))
    assert rows[-1]["model"] == "claude" and rows[-1]["score"] == 4 and rows[-1]["note"] == "clean diff"
    assert "kind" not in rows[-1]


def test_a_waiting_list_is_read_from_the_home_when_present(home, tmp_path):
    (home / "waiting.json").write_text(json.dumps([{"item": "x", "who": "you", "when": "soon"}]), encoding="utf-8")
    out = tmp_path / "out"
    dashdata.export(home, out, commands=56)
    assert json.loads((out / "waiting.json").read_text(encoding="utf-8")) == [{"item": "x", "who": "you", "when": "soon"}]


def test_without_a_waiting_file_the_list_is_empty_not_invented(home, tmp_path):
    out = tmp_path / "out"
    dashdata.export(home, out, commands=56)
    assert json.loads((out / "waiting.json").read_text(encoding="utf-8")) == []


def test_the_command_prints_what_it_wrote(home, tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("LIFEOS_HOME", str(home))
    assert main(["dash-export", "--out", str(tmp_path / "o")]) == 0
    out = capsys.readouterr().out
    assert "numbers.json" in out and "private" in out.lower()
