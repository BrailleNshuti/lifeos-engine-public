"""A short sharing violation on Windows (a scanner or reader holding a fresh file) is retried a few times; nothing else is."""
import json
import os
import subprocess
import sys

import pytest

from lifeos import diag, store

NT = os.name == "nt"


def violation(winerror=5):
    return PermissionError(13, "Access is denied", None, winerror)


@pytest.fixture
def pauses(monkeypatch):
    got = []
    monkeypatch.setattr(store, "_pause", got.append)
    return got


@pytest.fixture
def diag_file(tmp_path, monkeypatch):
    path = tmp_path / "diag.jsonl"
    monkeypatch.setenv(diag.ENV, str(path))
    return path


def events(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def fail_times(monkeypatch, n, err):
    calls = []
    real = os.replace

    def flaky(src, dst):
        calls.append(1)
        if len(calls) <= n:
            raise err
        real(src, dst)

    monkeypatch.setattr(store.os, "replace", flaky)
    return calls


@pytest.mark.skipif(not NT, reason="a sharing violation is a Windows condition")
@pytest.mark.parametrize("winerror", [5, 32])
def test_a_short_sharing_violation_is_retried_and_the_write_lands(tmp_path, monkeypatch, pauses, diag_file, winerror, capsys):
    calls = fail_times(monkeypatch, 2, violation(winerror))
    target = tmp_path / "ledger.csv"
    store.atomic_write_bytes(target, b"new")
    assert target.read_bytes() == b"new" and len(calls) == 3
    assert pauses == list(store.REPLACE_DELAYS[:2])
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == []
    assert capsys.readouterr().err == "", "a recovered write is not an error"
    (event,) = events(diag_file)
    assert event["event"] == "os.replace recovered" and event["attempts"] == 3 and event["winerror"] == winerror


@pytest.mark.skipif(not NT, reason="a sharing violation is a Windows condition")
def test_a_violation_that_never_goes_away_fails_after_a_bounded_number_of_tries(tmp_path, monkeypatch, pauses, diag_file):
    calls = fail_times(monkeypatch, 99, violation(5))
    with pytest.raises(PermissionError) as caught:
        store.atomic_write_bytes(tmp_path / "ledger.csv", b"new")
    assert caught.value.winerror == 5, "the original error, not a wrapper"
    assert len(calls) == len(store.REPLACE_DELAYS) + 1 and pauses == list(store.REPLACE_DELAYS)
    assert sum(store.REPLACE_DELAYS) < 2.0, "the wait is bounded and short"
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == []
    (event,) = events(diag_file)
    assert event["event"] == "os.replace failed" and event["attempts"] == len(store.REPLACE_DELAYS) + 1


@pytest.mark.parametrize("err", [
    PermissionError(13, "denied"),                    # no winerror: a plain permission problem, not a sharing violation
    PermissionError(13, "denied", None, 123),         # some other Windows error
    FileNotFoundError(2, "gone"),
])
def test_other_errors_are_raised_at_once(tmp_path, monkeypatch, pauses, diag_file, err):
    calls = fail_times(monkeypatch, 99, err)
    with pytest.raises(OSError):
        store.atomic_write_bytes(tmp_path / "x.txt", b"data")
    assert len(calls) == 1 and pauses == []


def test_only_windows_sharing_violations_count_as_transient(monkeypatch):
    assert not store._transient(PermissionError(13, "denied"))
    assert not store._transient(FileNotFoundError(2, "gone"))
    monkeypatch.setattr(store.os, "name", "nt")
    assert store._transient(violation(5)) and store._transient(violation(32)) and not store._transient(violation(123))
    monkeypatch.setattr(store.os, "name", "posix")
    assert not store._transient(violation(5))


def test_a_clean_write_pauses_never_and_logs_nothing(tmp_path, pauses, diag_file):
    store.atomic_write_bytes(tmp_path / "a.txt", b"hello")
    assert pauses == [] and not diag_file.exists()


HOLDER = "import sys, time\nf = open(sys.argv[1], 'rb')\nprint('held', flush=True)\ntime.sleep(float(sys.argv[2]))\n"


@pytest.mark.skipif(not NT, reason="Windows sharing rules")
def test_a_real_reader_that_lets_go_within_a_fraction_of_a_second_does_not_break_the_write(tmp_path, diag_file):
    target = tmp_path / "held.txt"
    target.write_text("old", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-c", HOLDER, str(target), "0.3"], stdout=subprocess.PIPE, text=True)
    try:
        proc.stdout.readline()
        store.atomic_write_bytes(target, b"new")  # fails at first (winerror 5), succeeds once the reader is gone
    finally:
        proc.kill()
        proc.wait()
    assert target.read_bytes() == b"new"
    assert [e["event"] for e in events(diag_file)] == ["os.replace recovered"]


@pytest.mark.skipif(not NT, reason="Windows sharing rules")
def test_a_reader_that_never_lets_go_still_fails_loudly(tmp_path, diag_file):
    target = tmp_path / "held.txt"
    target.write_text("old", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-c", HOLDER, str(target), "30"], stdout=subprocess.PIPE, text=True)
    try:
        proc.stdout.readline()
        with pytest.raises(PermissionError):
            store.atomic_write_bytes(target, b"new")
    finally:
        proc.kill()
        proc.wait()
    assert target.read_bytes() == b"old", "the old content is intact"
    assert [e["event"] for e in events(diag_file)] == ["os.replace failed"]
