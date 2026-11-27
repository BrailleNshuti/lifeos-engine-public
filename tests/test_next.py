"""`lifeos next` names the one thing to do now, in a fixed order (round 5 item 10). Made-up data only."""
import datetime as dt
import json

import pytest

from lifeos import nextup
from lifeos.cli import main

DAY = dt.date(2026, 11, 28)
TASK = "---\nid: {id}\ngoal: {goal}\ndone_when: a checkable finish line\nroute: claude\nlevel: L0\nstatus: {status}\ndue: {due}\n---\n## Proof\n"


@pytest.fixture
def home(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "now.md").write_text("# now", encoding="utf-8")
    return tmp_path


def task(home, id, goal="do the thing", status="todo", due=""):
    (home / "tasks" / f"{id}.md").write_text(TASK.format(id=id, goal=goal, status=status, due=due), encoding="utf-8")


def test_an_empty_home_suggests_starting_something(home):
    assert nextup.choose(home, DAY)["kind"] == "none"


def test_the_next_open_task_when_nothing_is_pressing(home):
    task(home, "T-261201-a", due="2026-12-05")
    c = nextup.choose(home, DAY)
    assert c["kind"] == "task" and c["command"] == "lifeos route T-261201-a"


def test_an_overdue_task_beats_everything_but_damaged_files(home):
    task(home, "T-261201-a", due="2026-12-05")
    task(home, "T-261120-late", goal="finish it", due="2026-11-25")
    (home / "waiting.json").write_text(json.dumps([{"item": "x", "who": "you", "when": "2026-11-28"}]), encoding="utf-8")
    assert nextup.choose(home, DAY)["kind"] == "overdue"


def test_a_blocked_task_is_not_suggested(home):
    task(home, "T-261120-late", due="2026-11-25", status="blocked")
    assert nextup.choose(home, DAY)["kind"] == "none"


def test_an_unrated_answer_comes_before_a_waiting_item(home):
    (home / "logs" / "runs.jsonl").write_text(json.dumps({"command": "ask", "model": "gemini", "status": "ok", "task_id": "T-261120-a", "date": "2026-11-25"}) + "\n", encoding="utf-8")
    (home / "waiting.json").write_text(json.dumps([{"item": "x", "who": "you", "when": "2026-11-29"}]), encoding="utf-8")
    c = nextup.choose(home, DAY)
    assert c["kind"] == "rate" and "lifeos rate T-261120-a gemini" in c["command"]


def test_a_waiting_item_due_soon_is_named_and_a_far_one_is_not(home):
    (home / "waiting.json").write_text(json.dumps([{"item": "far away", "who": "you", "when": "2026-12-20"}, {"item": "soon", "who": "you", "when": "2026-11-30"}]), encoding="utf-8")
    c = nextup.choose(home, DAY)
    assert c["kind"] == "waiting" and "soon" in c["text"] and "due in 2 day(s)" in c["text"]
    (home / "waiting.json").write_text(json.dumps([{"item": "far away", "who": "you", "when": "2026-12-20"}]), encoding="utf-8")
    assert nextup.choose(home, DAY)["kind"] == "none"


def test_damaged_files_come_first(home):
    (home / "waiting.json").write_text("{broken", encoding="utf-8")
    task(home, "T-261120-late", due="2026-11-25")
    c = nextup.choose(home, DAY)
    assert c["kind"] == "files" and c["command"] == "lifeos selfcheck"


def test_the_command_prints_one_decision(home, capsys):
    assert main(["--home", str(home), "next"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Next (") and "  Run: " in out
