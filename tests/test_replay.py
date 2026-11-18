import datetime as dt
import json
import shutil

import pytest

from lifeos import ask, replay
from lifeos.cli import main

TODAY = dt.date(2026, 11, 20)
CLEAN = "Updated tests/test_runs.py and verified output. Next step: run pytest."


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def do_run(home, rid="R-replay-1", full=False):
    ask.run_ask(home, "claude", "T-261116", adapters={"claude": lambda p: CLEAN}, today=TODAY, run_id=rid, full=full)


def test_run_record_stores_per_file_digests_but_no_content(home):
    do_run(home)
    rec = json.loads((home / "logs" / "runs.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    names = [f["name"] for f in rec["context_files"]]
    assert "rules.md" in names and any(n.startswith("tasks/") for n in names)
    assert all(len(f["sha256"]) == 64 and set(f) == {"name", "sha256", "status"} for f in rec["context_files"])
    assert isinstance(rec["task_chars"], int)


def test_replay_matches_even_though_the_answer_was_appended_to_the_task(home):
    do_run(home)
    out = replay.replay_run(home, "R-replay-1")
    assert out["supported"] and out["identical"] is True and out["changed"] == []


def test_replay_names_the_file_that_changed(home):
    do_run(home)
    rules = home / "rules.md"
    rules.write_text(rules.read_text(encoding="utf-8") + "\nA new rule.\n", encoding="utf-8")
    out = replay.replay_run(home, "R-replay-1")
    assert out["identical"] is False and out["changed"] == ["rules.md"]


def test_editing_earlier_task_text_is_detected(home):
    do_run(home)
    task = next((home / "tasks").glob("T-261116*.md"))
    text = task.read_text(encoding="utf-8")
    task.write_text(text.replace("goal:", "goal: CHANGED", 1), encoding="utf-8")
    out = replay.replay_run(home, "R-replay-1")
    assert out["identical"] is False and any(n.startswith("tasks/") for n in out["changed"])


def test_full_mode_runs_are_replayed_in_full_mode(home):
    do_run(home, full=True)
    out = replay.replay_run(home, "R-replay-1")
    assert out["identical"] is True and any(f["name"] == "now.md" for f in out["files"])


def test_old_records_without_digests_are_reported_not_guessed(home):
    do_run(home)
    path = home / "logs" / "runs.jsonl"
    rec = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    rec.pop("context_files"); rec.pop("task_chars")
    path.write_text(json.dumps(rec, sort_keys=True) + "\n", encoding="utf-8")
    out = replay.replay_run(home, "R-replay-1")
    assert out["supported"] is False and "before replay" in out["reason"]


def test_unknown_run_and_review_runs(home):
    with pytest.raises(replay.ReplayError, match="not found"):
        replay.replay_run(home, "R-nope")


def test_cli_exit_codes(home, capsys, monkeypatch):
    do_run(home)
    monkeypatch.setenv("LIFEOS_HOME", str(home))
    assert main(["replay", "R-replay-1"]) == 0
    assert "identical" in capsys.readouterr().out
    (home / "rules.md").write_text("# changed\n", encoding="utf-8")
    assert main(["replay", "R-replay-1"]) == 1
    assert "rules.md" in capsys.readouterr().out
    assert main(["replay", "R-nope"]) == 2
