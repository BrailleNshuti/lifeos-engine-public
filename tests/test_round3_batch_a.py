"""Round 3 items 3, 10, 13 and 16: lock timeout message, unusual home paths, redaction round trip, no text in the ledger."""
import json
import os
import shutil
import threading

import pytest

from lifeos import canary, guard, redact, store
from lifeos.cli import main

TOKEN = "ghp_" + "a1B2" * 9  # assembled at run time


# 3. a lock held longer than its timeout gives a clear error that names the lock
def test_a_held_lock_times_out_with_a_message_that_names_it(tmp_path):
    lock = tmp_path / "x.lock"
    held, release = threading.Event(), threading.Event()

    def holder():
        with store._advisory_lock_file(lock, timeout=5):
            held.set()
            release.wait(10)

    thread = threading.Thread(target=holder)
    thread.start()
    held.wait(5)
    try:
        other = {}

        def second():
            try:
                with store._advisory_lock_file(lock, timeout=0.3):
                    other["got"] = True
            except TimeoutError as err:
                other["err"] = str(err)

        t2 = threading.Thread(target=second)
        t2.start()
        t2.join(10)
    finally:
        release.set()
        thread.join(10)
    assert "got" not in other and "Timed out" in other["err"] and "x.lock" in other["err"]


# 10. LIFEOS_HOME with spaces, non-ASCII characters, a trailing separator and a relative path
@pytest.mark.parametrize("name", ["with space", "jürgen-日本", "plain"])
def test_the_home_may_have_spaces_and_non_ascii_characters(name, tmp_path, demo, monkeypatch, capsys):
    target = tmp_path / name
    shutil.copytree(demo, target)
    monkeypatch.setenv("LIFEOS_HOME", str(target) + os.sep)  # with a trailing separator
    assert main(["doctor"]) == 0
    assert main(["earn"]) == 0
    before = set((target / "tasks").iterdir())
    assert main(["task", "new", "check a path", "--level", "L0"]) == 0
    assert len(set((target / "tasks").iterdir()) - before) == 1  # one new task file inside the odd home


def test_a_relative_home_is_resolved(tmp_path, demo, monkeypatch):
    target = tmp_path / "rel home"
    shutil.copytree(demo, target)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LIFEOS_HOME", "rel home")
    assert main(["doctor"]) == 0


# 13. redact, then guard, finds nothing: for every canary kind and for a token split over two lines
def test_redacting_every_canary_leaves_nothing_for_the_guard():
    for kind, layout, text in canary.canaries(per_spec=1):
        clean, _count = redact.text(f"line before\n{text}\nline after\n")
        assert not [f for f in guard.scan_text(clean) if f[1] == "BLOCK"], (kind, layout)


def test_a_split_token_is_fully_redacted_not_half():
    content = f"intro\n{TOKEN[:12]}\n{TOKEN[12:]}\noutro\n"
    clean, count = redact.text(content)
    assert count >= 1
    assert TOKEN[:12] not in clean and TOKEN[12:] not in clean, clean
    assert clean.count("\n") == content.count("\n")  # the line count is kept


# 16. no prompt or answer text is written into the run ledger
def test_the_run_ledger_never_holds_prompt_or_answer_text(tmp_path, demo):
    from lifeos import ask
    home = tmp_path / "home"
    shutil.copytree(demo, home)
    marker = "UNIQUE-ANSWER-MARKER-4711"
    ask.run_ask(home, "fake", "T-261116", adapters={"fake": lambda prompt: f"answer {marker} with https://example.org 2026-11-27"})
    ledger = (home / "logs" / "runs.jsonl").read_text(encoding="utf-8")
    assert marker not in ledger
    assert "Ship the context command" not in ledger  # the task goal (prompt text) is not in it either
    for line in ledger.splitlines():
        record = json.loads(line)
        assert all(not isinstance(v, str) or len(v) < 300 for v in record.values()), record
