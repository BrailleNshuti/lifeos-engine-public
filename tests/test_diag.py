"""Failure-only diagnostics for os.replace: record the error code, the paths and who holds the file; never retry, never mask."""
import json
import os
import subprocess
import sys
import time

import pytest

from lifeos import diag, store


@pytest.fixture
def diag_file(tmp_path, monkeypatch):
    path = tmp_path / "diag.jsonl"
    monkeypatch.setenv(diag.ENV, str(path))
    return path


def lines(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def test_a_successful_write_leaves_no_diagnostic(tmp_path, diag_file):
    store.atomic_write_bytes(tmp_path / "a.txt", b"hello")
    assert (tmp_path / "a.txt").read_bytes() == b"hello" and not diag_file.exists()


def test_a_failed_replace_is_recorded_once_raised_unchanged_and_never_retried(tmp_path, diag_file, monkeypatch):
    calls = []

    def denied(src, dst):
        calls.append((str(src), str(dst)))
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(store.os, "replace", denied)
    target = tmp_path / "ledger.csv"
    with pytest.raises(PermissionError) as caught:
        store.atomic_write_bytes(target, b"data")
    assert caught.value.errno == 13 and len(calls) == 1, "must not retry"
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == [], "the temp file is cleaned up"
    (rec,) = lines(diag_file)
    assert rec["errno"] == 13 and rec["dst"] == str(target) and rec["src"].endswith(".tmp") and rec["pid"] == os.getpid()
    assert rec["event"] == "os.replace failed" and "holders_dst" in rec and "own_pid_holds" in rec and rec["time"]


def test_other_errors_are_not_diagnosed(tmp_path, diag_file, monkeypatch):
    def missing(src, dst):
        raise FileNotFoundError(2, "gone")

    monkeypatch.setattr(store.os, "replace", missing)
    with pytest.raises(FileNotFoundError):
        store.atomic_write_bytes(tmp_path / "x.txt", b"data")
    assert not diag_file.exists()


def test_a_broken_diagnostic_never_hides_the_real_error(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("diagnostic bug")

    monkeypatch.setenv(diag.ENV, str(tmp_path / "no" / "such" / "dir" / "d.jsonl"))
    monkeypatch.setattr(diag, "describe", boom)
    monkeypatch.setattr(store.os, "replace", lambda s, d: (_ for _ in ()).throw(PermissionError(13, "denied")))
    with pytest.raises(PermissionError):
        store.atomic_write_bytes(tmp_path / "y.txt", b"data")


def test_an_unwritable_diagnostic_file_does_not_matter(tmp_path, monkeypatch):
    monkeypatch.setenv(diag.ENV, str(tmp_path / "no" / "such" / "dir" / "d.jsonl"))
    assert diag.report(PermissionError(13, "denied"), tmp_path / "a.tmp", tmp_path / "a") is None


def test_the_report_goes_to_stderr_even_without_a_file(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(diag.ENV, raising=False)
    diag.report(PermissionError(13, "denied"), tmp_path / "a.tmp", tmp_path / "a")
    err = capsys.readouterr().err
    assert "os.replace failed" in err and "errno=13" in err


HOLDER = "import sys, time\nf = open(sys.argv[1], 'rb')\nprint('held', flush=True)\ntime.sleep(30)\n"


@pytest.fixture
def holder(tmp_path):
    target = tmp_path / "held.txt"
    target.write_text("old", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-c", HOLDER, str(target)], stdout=subprocess.PIPE, text=True)
    proc.stdout.readline()
    yield target, proc
    proc.kill()
    proc.wait()


@pytest.mark.skipif(os.name != "nt", reason="Windows Restart Manager")
def test_holders_names_the_process_that_has_the_file_open(holder):
    target, proc = holder
    found = diag.holders(target)
    assert proc.pid in [h["pid"] for h in found], found


@pytest.mark.skipif(os.name != "nt", reason="Windows sharing rules")
def test_a_real_sharing_violation_is_diagnosed_with_the_holder_and_is_not_our_own_process(holder, diag_file):
    target, proc = holder
    with pytest.raises(PermissionError):
        store.atomic_write_bytes(target, b"new")
    (rec,) = lines(diag_file)
    assert rec["winerror"] in (5, 32)
    assert proc.pid in [h["pid"] for h in rec["holders_dst"]]
    assert rec["own_pid_holds"] is False


def test_holders_is_empty_where_there_is_no_restart_manager(tmp_path, monkeypatch):
    monkeypatch.setattr(diag.os, "name", "posix")
    assert diag.holders(tmp_path / "anything") == []
