"""Readers of files that are replaced atomically wait out a short Windows sharing violation (round 5 item 1)."""
import json
from pathlib import Path

import pytest

from lifeos import store, tasks, today, waiting


def sharing_violation():
    err = PermissionError(13, "sharing violation")
    err.winerror = 32
    return err


@pytest.fixture
def flaky(monkeypatch):
    """Make the first read of every file fail once with a sharing violation, as if a replace were in progress."""
    seen = set()
    real = Path.read_bytes

    def read_bytes(self):
        if str(self) not in seen:
            seen.add(str(self))
            raise sharing_violation()
        return real(self)
    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    monkeypatch.setattr(store, "_read_transient", lambda err: True)  # the retry is Windows-only; force it so this runs everywhere
    monkeypatch.setattr(store, "_pause", lambda s: None)
    return seen


def test_a_read_that_meets_a_swap_tries_again(tmp_path, flaky):
    (tmp_path / "x.txt").write_bytes(b"hello")
    assert store.read_bytes_retry(tmp_path / "x.txt") == b"hello"
    assert len(flaky) == 1


def test_a_lasting_lock_still_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_read_transient", lambda err: True)
    monkeypatch.setattr(store, "_pause", lambda s: None)
    monkeypatch.setattr(Path, "read_bytes", lambda self: (_ for _ in ()).throw(sharing_violation()))
    with pytest.raises(PermissionError):
        store.read_bytes_retry(tmp_path / "x.txt")


def test_other_errors_are_not_retried(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(Path, "read_bytes", lambda self: calls.append(1) or (_ for _ in ()).throw(FileNotFoundError(2, "gone")))
    with pytest.raises(FileNotFoundError):
        store.read_bytes_retry(tmp_path / "x.txt")
    assert len(calls) == 1


def test_a_plain_permission_error_is_retried_only_on_windows(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(store, "_pause", lambda s: None)
    monkeypatch.setattr(Path, "read_bytes", lambda self: calls.append(1) or (_ for _ in ()).throw(PermissionError(13, "denied")))
    with pytest.raises(PermissionError):
        store.read_bytes_retry(tmp_path / "x.txt")
    import os
    assert len(calls) == (len(store.REPLACE_DELAYS) + 1 if os.name == "nt" else 1)


def test_task_files_ratings_and_the_waiting_list_survive_a_swap(tmp_path, flaky):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-261128-a.md").write_text("---\nid: T-261128-a\nstatus: todo\n---\n", encoding="utf-8")
    (tmp_path / "ratings.csv").write_text("date,task\n2026-11-28,T-1\n", encoding="utf-8")
    (tmp_path / "waiting.json").write_text(json.dumps([{"item": "x", "who": "you", "when": "soon"}]), encoding="utf-8")
    assert tasks.read_frontmatter(tmp_path / "tasks" / "T-261128-a.md")["status"] == "todo"
    assert store.read_csv_rows(tmp_path / "ratings.csv", ("task",))[0]["task"] == "T-1"
    assert waiting.read(tmp_path)[0]["item"] == "x"
    assert today.read_waiting(tmp_path)[0]["item"] == "x"
