"""Round 3 items 2, 4, 6, 7 and 9: the store under crashes, a full disk, two processes and a big ledger; window edges."""
import csv
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from lifeos import earn, egress, store, sunday

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


# 4. a process killed between the files of a multi-file commit: the journal brings the store back to a whole state
CRASH_CHILD = """
import os, sys
sys.path.insert(0, sys.argv[2])
from pathlib import Path
from lifeos import store
home = Path(sys.argv[1])
real = store.atomic_write_bytes
calls = {"n": 0}
def dying(path, data):
    real(path, data)
    calls["n"] += 1
    if calls["n"] == 2:        # journal written (1st) and the first target written (2nd): die before the second target
        os._exit(7)
store.atomic_write_bytes = dying
task = next((home / "tasks").glob("T-261116*.md"))
store.commit_transaction(home, [(task, b"NEW TASK"), (home / "logs" / "ledger.csv", b"NEW LEDGER")])
"""


def test_a_crash_between_two_files_is_repaired_by_the_journal(home):
    task = next((home / "tasks").glob("T-261116*.md"))
    ledger = home / "logs" / "ledger.csv"
    old_ledger = ledger.read_bytes()
    child = subprocess.run([sys.executable, "-c", CRASH_CHILD, str(home), str(ROOT)], capture_output=True, text=True)
    assert child.returncode == 7, child.stderr[-300:]
    assert task.read_bytes() == b"NEW TASK" and ledger.read_bytes() == old_ledger  # torn: one file new, the other old
    assert (home / "logs" / ".store.journal.json").exists()
    assert store.recover_journal(home) is True
    assert ledger.read_bytes() == b"NEW LEDGER" and task.read_bytes() == b"NEW TASK"
    assert not (home / "logs" / ".store.journal.json").exists()
    assert store.recover_journal(home) is False  # nothing left to replay


# 6. a full disk: the old content stays whole and no temp file is left behind
def full_disk(fd, data):
    raise OSError(28, "No space left on device")


def tmp_files(folder):
    return [p.name for p in Path(folder).iterdir() if p.name.endswith(".tmp")]


def test_a_full_disk_leaves_the_old_file_and_no_temp_file(home, monkeypatch):
    target = home / "logs" / "ledger.csv"
    before = target.read_bytes()
    monkeypatch.setattr(store, "_write_all", full_disk)
    with pytest.raises(OSError):
        store.atomic_write_bytes(target, b"x" * 1000)
    assert target.read_bytes() == before and not tmp_files(home / "logs")


def test_a_full_disk_during_a_csv_append_changes_nothing(home, monkeypatch):
    target = home / "logs" / "ledger.csv"
    before = target.read_bytes()
    monkeypatch.setattr(store, "_write_all", full_disk)
    with pytest.raises(OSError):
        store.append_csv_row(target, ["2026-11-27", "T-1", "claude", "", "note"])
    assert target.read_bytes() == before and not tmp_files(home / "logs")


def test_a_full_disk_during_an_answer_changes_no_file_and_shows_the_answer(home, monkeypatch):
    from lifeos import ask
    task = next((home / "tasks").glob("T-261116*.md"))
    before = {p: p.read_bytes() for p in (task, home / "logs" / "ledger.csv")}
    monkeypatch.setattr(store, "_write_all", full_disk)
    with pytest.raises(ask.AskError) as raised:
        ask.run_ask(home, "fake", "T-261116", adapters={"fake": lambda prompt: "AN ANSWER"})
    assert raised.value.answer == "AN ANSWER"
    assert {p: p.read_bytes() for p in before} == before and not tmp_files(home / "logs")


# 2. two processes recording results at once: nothing lost, nothing half committed
RESULT_CHILD = """
import sys
sys.path.insert(0, sys.argv[4])
from pathlib import Path
from lifeos import ask
home, tag, count = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
for i in range(count):
    ask.run_ask(home, "fake", "T-261116", adapters={"fake": lambda prompt: f"answer {tag}-{i} https://example.org 2026-11-27 next"})
"""


def test_two_processes_recording_results_lose_nothing(home):
    per = 12
    task = next((home / "tasks").glob("T-261116*.md"))
    ledger_before = len((home / "logs" / "ledger.csv").read_text(encoding="utf-8").splitlines())
    runs_before = len((home / "logs" / "runs.jsonl").read_text(encoding="utf-8").splitlines()) if (home / "logs" / "runs.jsonl").exists() else 0
    procs = [subprocess.Popen([sys.executable, "-c", RESULT_CHILD, str(home), tag, str(per), str(ROOT)], stderr=subprocess.PIPE, text=True)
             for tag in ("a", "b")]
    for p in procs:
        _, err = p.communicate(timeout=180)
        assert p.returncode == 0, err[-300:]
    text = task.read_text(encoding="utf-8")
    assert text.count("## Result · fake") == 2 * per
    assert len((home / "logs" / "ledger.csv").read_text(encoding="utf-8").splitlines()) == ledger_before + 2 * per
    assert len((home / "logs" / "runs.jsonl").read_text(encoding="utf-8").splitlines()) == runs_before + 2 * per
    assert not (home / "logs" / ".store.journal.json").exists()


# 7. a big ledger does not make the reports slow
def test_a_big_run_ledger_keeps_the_reports_fast(home):
    today = dt.date(2026, 11, 27)
    records = [{"command": "ask", "model": ("claude", "codex", "gemini", "grok")[i % 4], "status": "ok" if i % 9 else "failed",
                "duration_ms": 1000 + i % 5000, "tokens": 1500, "date": (today - dt.timedelta(days=i % 40)).isoformat()}
               for i in range(30000)]
    (home / "logs" / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    start = time.perf_counter()
    earn.review(home, today=today)
    earn.latency(home, today=today)
    egress.report(home, today=today)
    assert time.perf_counter() - start < 10, "the three reports on 30,000 records took too long"
    assert "Sunday review" in sunday.build(home, today=today)


# 9. the 30-day window has exact edges
def test_the_window_includes_today_and_excludes_the_30th_day_back_and_the_future(home):
    today = dt.date(2026, 11, 27)

    def rec(offset):
        return {"command": "ask", "model": "claude", "status": "ok", "duration_ms": 1000, "tokens": 100,
                "date": (today + dt.timedelta(days=offset)).isoformat()}

    (home / "logs" / "runs.jsonl").write_text("".join(json.dumps(rec(o)) + "\n" for o in (-30, -29, 0, 1)), encoding="utf-8")
    assert egress.report(home, today=today, days=30)[0]["calls"] == 2  # day -29 and today; -30 and tomorrow are out
    assert earn.latency(home, today=today, days=30)[0]["ok"] == 2
