"""`lifeos rate --walk` rates the unrated answers at the prompt (round 5 item 7). Made-up data only."""
import datetime as dt
import json

import pytest

from lifeos import learn, ratewalk
from lifeos.cli import main

DAY = dt.date(2026, 11, 28)
TASK = "---\nid: {id}\ngoal: a goal\ndone_when: a checkable finish line\nroute: claude\nlevel: L0\nstatus: done\ndue: \n---\n## Result · gemini · 2026-11-25\nThe answer says the fine is 1000 euros. Next: none.\n## Proof\ntests/a.py\n"


@pytest.fixture
def home(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "now.md").write_text("# now", encoding="utf-8")
    for tid in ("T-261125-a", "T-261125-b"):
        (tmp_path / "tasks" / f"{tid}.md").write_text(TASK.format(id=tid), encoding="utf-8")
    runs = [{"command": "ask", "model": "gemini", "status": "ok", "task_id": tid, "date": "2026-11-25"} for tid in ("T-261125-a", "T-261125-b")]
    (tmp_path / "logs" / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in runs), encoding="utf-8")
    return tmp_path


def scripted(*answers):
    it = iter(answers)
    return lambda prompt="": next(it)


def test_rating_both_answers_saves_both(home):
    out = []
    n = ratewalk.walk(home, ask=scripted("4", "good and sourced", "3", ""), say=out.append, day=DAY)
    assert n == 2
    rows = learn.read_ratings(home)
    assert [(r["task"], r["model"], r["score"]) for r in rows] == [("T-261125-a", "gemini", 4), ("T-261125-b", "gemini", 3)]
    assert rows[0]["note"] == "good and sourced"
    assert any("answer starts: The answer says the fine is 1000 euros" in line for line in out)


def test_skip_and_stop(home):
    assert ratewalk.walk(home, ask=scripted("s", "q"), say=lambda *_: None, day=DAY) == 0
    assert learn.read_ratings(home) == []


def test_a_low_score_needs_a_note(home):
    n = ratewalk.walk(home, ask=scripted("1", "", "q"), say=lambda *_: None, day=DAY)
    assert n == 0 and learn.read_ratings(home) == []


def test_junk_input_asks_again(home):
    out = []
    ratewalk.walk(home, ask=scripted("nine", "7", "5", "fine", "q"), say=out.append, day=DAY)
    assert out.count("  type a number from 1 to 5, s or q") == 2
    assert len(learn.read_ratings(home)) == 1


def test_nothing_to_rate(home):
    learn.add_rating(home, "T-261125-a", "gemini", 4, "x")
    learn.add_rating(home, "T-261125-b", "gemini", 4, "x")
    out = []
    assert ratewalk.walk(home, ask=scripted(), say=out.append, day=DAY) == 0
    assert out == ["Every answer is rated."]


def test_the_old_form_still_works_and_a_bare_rate_explains(home, capsys, monkeypatch):
    monkeypatch.setenv("LIFEOS_HOME", str(home))
    assert main(["rate", "T-261125-a", "gemini", "4"]) == 0
    assert main(["rate"]) == 2
    assert "--walk" in capsys.readouterr().err


def test_a_task_archived_after_the_list_was_built_is_explained(home, monkeypatch):
    item = {"task": "T-261125-gone", "seat": "gemini", "date": "2026-11-25"}
    monkeypatch.setattr(ratewalk.today, "unrated", lambda *_: [item])
    out = []
    assert ratewalk.walk(home, ask=scripted(), say=out.append, day=DAY) == 0
    assert any("task file" in line and "skipped" in line for line in out)


def test_a_read_error_and_end_of_input_stop_cleanly(home, monkeypatch):
    original = ratewalk.read_text_retry
    monkeypatch.setattr(ratewalk, "read_text_retry", lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError(13, "locked")))
    out = []
    assert ratewalk.walk(home, ask=scripted(), say=out.append, day=DAY) == 0
    assert any("could not read" in line and "skipped" in line for line in out)

    monkeypatch.setattr(ratewalk, "read_text_retry", original)
    out = []
    assert ratewalk.walk(home, ask=lambda *_: (_ for _ in ()).throw(EOFError()), say=out.append, day=DAY) == 0
    assert "  stopped." in out and out[-1] == "0 rating(s) saved."
