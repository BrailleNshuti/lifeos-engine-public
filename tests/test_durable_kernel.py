"""Tests for Execution Kernel Durable: pre-execution run_id idempotency (ask + review), transactional journal
recovery and path-allowlist security, exclusive file locking (live-PID stale protection + token-checked release +
8-thread concurrency across task/ledger/runs), failed/blocked/timeout/partial/full-fail run logging with redaction,
64-char SHA-256 digests, CLI doctor --tools/--live exit codes, and per-reviewer isolated git worktree blind reviews."""
import base64
import datetime as dt
import json
import os
import shutil
import subprocess
import threading
import time
import pytest

from lifeos import ask, cli, context, store

TODAY = dt.date(2026, 11, 20)
CLEAN = "Verified lifeos/store.py and tests/test_durable_kernel.py. Next step: merge."


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def _read_runs(home):
    path = home / "logs" / "runs.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_pre_execution_run_id_idempotency_prevents_duplicate_ask_and_review(home, monkeypatch):
    ask_calls = []
    rev_calls = []

    def counting_ask(prompt):
        ask_calls.append(prompt)
        return CLEAN

    def counting_rev(prompt):
        rev_calls.append(prompt)
        return CLEAN

    task_path = home / "tasks" / "T-261116-demo-cli.md"
    before_ledger = (home / "logs" / "ledger.csv").read_text(encoding="utf-8").splitlines()

    # 1. Ask idempotency on retry with same run_id (both API and CLI --run-id)
    ask.run_ask(
        home, "fake", "T-261116", adapters={"fake": counting_ask}, today=TODAY, run_id="R-261120-idem0001"
    )
    after_first_ask = task_path.read_text(encoding="utf-8")
    ask.run_ask(
        home, "fake", "T-261116", adapters={"fake": counting_ask}, today=TODAY, run_id="R-261120-idem0001"
    )
    assert len(ask_calls) == 1
    assert task_path.read_text(encoding="utf-8") == after_first_ask
    assert len((home / "logs" / "ledger.csv").read_text(encoding="utf-8").splitlines()) == len(before_ledger) + 1

    # 2. Review idempotency on retry with same parent run_id
    ask.run_review(
        home, "T-261116", reviewers=("r1", "r2"),
        adapters={"r1": counting_rev, "r2": counting_rev}, today=TODAY, run_id="R-261120-revidem1",
    )
    after_first_rev = task_path.read_text(encoding="utf-8")
    ledger_after_rev = (home / "logs" / "ledger.csv").read_text(encoding="utf-8").splitlines()
    runs_after_rev = _read_runs(home)
    assert len(rev_calls) == 2

    # Retry with the same group run_id: zero additional provider calls, zero duplicate task/ledger/run records
    ask.run_review(
        home, "T-261116", reviewers=("r1", "r2"),
        adapters={"r1": counting_rev, "r2": counting_rev}, today=TODAY, run_id="R-261120-revidem1",
    )
    assert len(rev_calls) == 2
    assert task_path.read_text(encoding="utf-8") == after_first_rev
    assert (home / "logs" / "ledger.csv").read_text(encoding="utf-8").splitlines() == ledger_after_rev
    assert _read_runs(home) == runs_after_rev

    # 3. Crash after first child completes before parent review_group record is written:
    #    retrying the same parent run_id reuses child 1 without re-calling r1 and completes child 2 + parent
    class SimulatedProcessCrash(BaseException):
        pass

    r1_calls = []
    r2_calls = []

    def r1_ok(prompt):
        r1_calls.append(prompt)
        return CLEAN

    def r2_crash_once(prompt):
        r2_calls.append(prompt)
        if len(r2_calls) == 1:
            raise SimulatedProcessCrash("simulated uncatchable process crash after child 1 committed")
        return CLEAN

    with pytest.raises(SimulatedProcessCrash, match="simulated uncatchable process crash"):
        ask.run_review(
            home, "T-261116", reviewers=("r1", "r2"),
            adapters={"r1": r1_ok, "r2": r2_crash_once}, today=TODAY, run_id="R-261120-revcrash",
        )
    assert len(r1_calls) == 1 and len(r2_calls) == 1
    assert store.get_run_record(home, "R-261120-revcrash-c1") is not None
    assert store.get_run_record(home, "R-261120-revcrash") is None

    # Retry with same parent run_id: r1 is NOT called again, r2 completes, and parent record is written
    out_retry = ask.run_review(
        home, "T-261116", reviewers=("r1", "r2"),
        adapters={"r1": r1_ok, "r2": r2_crash_once}, today=TODAY, run_id="R-261120-revcrash",
    )
    assert len(r1_calls) == 1  # Zero duplicate calls to child 1!
    assert len(r2_calls) == 2
    assert out_retry["group_run_id"] == "R-261120-revcrash"
    parent_after = store.get_run_record(home, "R-261120-revcrash")
    assert parent_after is not None and parent_after["status"] == "ok"
    assert parent_after["child_run_ids"] == ["R-261120-revcrash-c1", "R-261120-revcrash-c2"]

    # 3b. Crash after child 1 commits, then mutating the task context before retry is rejected with ValueError
    crash_task = home / "tasks" / "T-261120-ctxmut.md"
    crash_task.write_text("# Original task facts\n", encoding="utf-8")
    r2_ctx_calls = []

    def r2_ctx_crash(prompt):
        r2_ctx_calls.append(prompt)
        if len(r2_ctx_calls) == 1:
            raise SimulatedProcessCrash("crash after child 1")
        return CLEAN

    with pytest.raises(SimulatedProcessCrash):
        ask.run_review(
            home, "T-261120-ctxmut", reviewers=("r1", "r2"),
            adapters={"r1": r1_ok, "r2": r2_ctx_crash}, today=TODAY, run_id="R-261120-revcrashctx",
        )
    crash_task.write_text("# Mutated task facts after child 1 committed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="already belongs to a different context or commit"):
        ask.run_review(
            home, "T-261120-ctxmut", reviewers=("r1", "r2"),
            adapters={"r1": r1_ok, "r2": r2_ctx_crash}, today=TODAY, run_id="R-261120-revcrashctx",
        )

    # 4. Mismatched run_id reuse across command, task, model, reviewer list, budget, full, parent_run_id, or diff_text
    #    is rejected with ValueError, zero additional provider calls, and no new run records
    other_task = home / "tasks" / "T-261120-other.md"
    other_task.write_text("# Other task\n", encoding="utf-8")
    runs_before_mismatch = _read_runs(home)
    ask_calls_before = len(ask_calls)
    rev_calls_before = len(rev_calls)
    with pytest.raises(ValueError, match="already belongs to a different operation"):
        ask.run_ask(home, "other_model", "T-261116", adapters={"other_model": counting_ask}, today=TODAY, run_id="R-261120-idem0001")
    with pytest.raises(ValueError, match="already belongs to a different operation"):
        ask.run_ask(home, "fake", "T-261120-other", adapters={"fake": counting_ask}, today=TODAY, run_id="R-261120-idem0001")
    with pytest.raises(ValueError, match="already belongs to budget"):
        ask.run_ask(home, "fake", "T-261116", budget=1500, adapters={"fake": counting_ask}, today=TODAY, run_id="R-261120-idem0001")
    with pytest.raises(ValueError, match="already belongs to full="):
        ask.run_ask(home, "fake", "T-261116", full=True, adapters={"fake": counting_ask}, today=TODAY, run_id="R-261120-idem0001")
    with pytest.raises(ValueError, match="already belongs to parent_run_id"):
        ask.run_ask(home, "fake", "T-261116", parent_run_id="R-261120-parent99", adapters={"fake": counting_ask}, today=TODAY, run_id="R-261120-idem0001")
    with pytest.raises(ValueError, match="already belongs to a different operation"):
        ask.run_review(home, "T-261116", reviewers=("r1",), adapters={"r1": counting_rev}, today=TODAY, run_id="R-261120-idem0001")
    with pytest.raises(ValueError, match="already belongs to a different operation"):
        ask.run_ask(home, "fake", "T-261116", adapters={"fake": counting_ask}, today=TODAY, run_id="R-261120-revidem1")
    with pytest.raises(ValueError, match="already belongs to a different operation"):
        ask.run_review(home, "T-261116", reviewers=("r1",), adapters={"r1": counting_rev}, today=TODAY, run_id="R-261120-revidem1")
    with pytest.raises(ValueError, match="already belongs to a different operation"):
        ask.run_review(home, "T-261120-other", reviewers=("r1", "r2"), adapters={"r1": counting_rev, "r2": counting_rev}, today=TODAY, run_id="R-261120-revidem1")
    with pytest.raises(ValueError, match="already belongs to budget"):
        ask.run_review(home, "T-261116", reviewers=("r1", "r2"), budget=1500, adapters={"r1": counting_rev, "r2": counting_rev}, today=TODAY, run_id="R-261120-revidem1")
    with pytest.raises(ValueError, match="already belongs to a different diff_text"):
        ask.run_review(home, "T-261116", reviewers=("r1", "r2"), diff_text="--- a/x.py\n+++ b/x.py\n", adapters={"r1": counting_rev, "r2": counting_rev}, today=TODAY, run_id="R-261120-revidem1")
    assert len(ask_calls) == ask_calls_before
    assert len(rev_calls) == rev_calls_before
    assert _read_runs(home) == runs_before_mismatch

    # 5. Simultaneous concurrent retries with the same run_id (ask and review) execute the provider only once,
    #    never time out at 30s when waiting on a slow provider (>35s simulated elapsed time), and return cleanly in both threads
    simul_ask_calls = []
    ask_outcomes = []
    ask_errors = []
    real_monotonic = store.time.monotonic
    clock_offset = {"sec": 0.0}
    monkeypatch.setattr(store.time, "monotonic", lambda: real_monotonic() + clock_offset["sec"])

    def slow_ask(prompt):
        time.sleep(0.05)
        clock_offset["sec"] += 35.0  # Simulate >30s provider execution while second thread waits on run_lock
        simul_ask_calls.append(prompt)
        return CLEAN

    def run_ask_worker():
        try:
            ask_outcomes.append(
                ask.run_ask(home, "fake", "T-261116", adapters={"fake": slow_ask}, today=TODAY, run_id="R-261120-simulask")
            )
        except BaseException as exc:
            ask_errors.append(exc)

    t_ask1 = threading.Thread(target=run_ask_worker)
    t_ask2 = threading.Thread(target=run_ask_worker)
    t_ask1.start()
    t_ask2.start()
    t_ask1.join()
    t_ask2.join()
    monkeypatch.setattr(store.time, "monotonic", real_monotonic)
    assert ask_errors == []
    assert len(ask_outcomes) == 2 and ask_outcomes[0] == task_path and ask_outcomes[1] == task_path
    assert len(simul_ask_calls) == 1

    simul_rev_calls = []
    rev_outcomes = []
    rev_errors = []

    def slow_rev(prompt):
        time.sleep(0.04)
        simul_rev_calls.append(prompt)
        return CLEAN

    def run_rev_worker():
        try:
            rev_outcomes.append(
                ask.run_review(
                    home, "T-261116", reviewers=("r1", "r2"),
                    adapters={"r1": slow_rev, "r2": slow_rev}, today=TODAY, run_id="R-261120-simulrev",
                )
            )
        except BaseException as exc:
            rev_errors.append(exc)

    t_rev1 = threading.Thread(target=run_rev_worker)
    t_rev2 = threading.Thread(target=run_rev_worker)
    t_rev1.start()
    t_rev2.start()
    t_rev1.join()
    t_rev2.join()
    assert rev_errors == []
    assert len(rev_outcomes) == 2 and all(o["group_run_id"] == "R-261120-simulrev" for o in rev_outcomes)
    assert len(simul_rev_calls) == 2


def test_transactional_journal_recovers_partial_crash_and_rejects_unsafe_paths(home, monkeypatch, tmp_path):
    task_path = home / "tasks" / "T-261116-demo-cli.md"
    ledger_path = home / "logs" / "ledger.csv"
    runs_path = home / "logs" / "runs.jsonl"

    real_replace = store.os.replace
    calls = {"n": 0}

    def crashing_replace(src, dst):
        calls["n"] += 1
        # Allow the journal write (call 1) and the first target file (call 2), then simulate a process crash!
        if calls["n"] == 3:
            raise OSError("simulated mid-transaction crash after first file")
        return real_replace(src, dst)

    monkeypatch.setattr(store.os, "replace", crashing_replace)
    rec = {
        "run_id": "R-261120-crash001",
        "date": TODAY.isoformat(),
        "command": "ask",
        "task_id": "T-261116-demo-cli",
        "model": "fake",
        "status": "ok",
    }
    with pytest.raises(OSError, match="simulated mid-transaction crash"):
        store.record_result(home, task_path, "fake", CLEAN, TODAY, note="asked via lifeos ask; flags: 0",
                            run_id="R-261120-crash001", run_record=rec)

    journal_path = home / "logs" / ".store.journal.json"
    assert journal_path.exists()

    # Restore os.replace and trigger recovery
    monkeypatch.setattr(store.os, "replace", real_replace)
    store.recover_journal(home)
    assert not journal_path.exists()
    assert "## Result · fake · 2026-11-20\n" + CLEAN in task_path.read_text(encoding="utf-8")
    assert "R-261120-crash001" in runs_path.read_text(encoding="utf-8")
    assert "T-261116-demo-cli,fake," in ledger_path.read_text(encoding="utf-8")

    # Retrying the same run_id after recovery is a no-op
    assert store.record_result(home, task_path, "fake", CLEAN, TODAY, note="asked via lifeos ask; flags: 0",
                               run_id="R-261120-crash001", run_record=rec) is False

    # Security: crafted journal targeting a file outside home or an unapproved file (rules.md) is refused and quarantined
    outside_target = tmp_path / "outside.txt"
    outside_target.write_text("SAFE", encoding="utf-8")
    rules_before = (home / "rules.md").read_text(encoding="utf-8")

    for bad_path in (str(outside_target), "../outside.txt", "rules.md", "tasks/../../outside.txt"):
        journal_path.write_text(
            json.dumps({
                "operations": [{"path": bad_path, "b64": base64.b64encode(b"PWNED").decode("ascii")}]
            }),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="Refused"):
            store.recover_journal(home)
        assert not journal_path.exists()
        assert outside_target.read_text(encoding="utf-8") == "SAFE"
        assert (home / "rules.md").read_text(encoding="utf-8") == rules_before
    # Corrupted/refused journals are quarantined rather than silently lost
    quarantined = list((home / "logs").glob(".store.journal.corrupt.*.json"))
    assert len(quarantined) == 4
    for q in quarantined:
        q.unlink()

    # Short-write resilience: _write_all loops over memoryview when os.write writes only a few bytes at a time
    real_write = store.os.write
    chunk_target = tmp_path / "chunked.txt"
    payload = b"abcdefghijklmnopqrstuvwxyz0123456789" * 3
    monkeypatch.setattr(store.os, "write", lambda fd, buf: real_write(fd, buf[:5]))
    store.atomic_write_bytes(chunk_target, payload)
    monkeypatch.setattr(store.os, "write", real_write)
    assert chunk_target.read_bytes() == payload

    # Zero-byte write raises OSError instead of spinning forever
    monkeypatch.setattr(store.os, "write", lambda fd, buf: 0)
    with pytest.raises(OSError, match="Short write returned 0 bytes"):
        store.atomic_write_bytes(chunk_target, b"fail")
    monkeypatch.setattr(store.os, "write", real_write)

    # Real POSIX parent-directory fsync body tested across commit_transaction, recover_journal, and _quarantine_journal
    import errno
    real_supports_dir_fsync = store._SUPPORTS_DIR_FSYNC
    real_open = store.os.open
    real_fsync = store.os.fsync
    real_close = store.os.close
    dir_events = []
    DIR_FD = 888888

    def posix_open(path_str, flags, *a, **kw):
        if flags == store.os.O_RDONLY and store.Path(path_str).is_dir():
            dir_events.append(("open", store.Path(path_str).name))
            return DIR_FD
        return real_open(path_str, flags, *a, **kw)

    def posix_fsync(fd):
        if fd == DIR_FD:
            dir_events.append(("fsync", DIR_FD))
            return
        return real_fsync(fd)

    def posix_close(fd):
        if fd == DIR_FD:
            dir_events.append(("close", DIR_FD))
            return
        return real_close(fd)

    monkeypatch.setattr(store, "_SUPPORTS_DIR_FSYNC", True)
    monkeypatch.setattr(store.os, "open", posix_open)
    monkeypatch.setattr(store.os, "fsync", posix_fsync)
    monkeypatch.setattr(store.os, "close", posix_close)
    try:
        store.commit_transaction(home, [
            (task_path, task_path.read_bytes()),
            (ledger_path, ledger_path.read_bytes()),
        ])
        # Recovery path also fsyncs parent directory
        journal_path.write_text(
            json.dumps({
                "operations": [{"path": "logs/ledger.csv", "b64": base64.b64encode(ledger_path.read_bytes()).decode("ascii")}]
            }),
            encoding="utf-8",
        )
        assert store.recover_journal(home) is True
        # Quarantine path also fsyncs parent directory
        journal_path.write_text("{corrupt", encoding="utf-8")
        with pytest.raises(ValueError, match="Refused"):
            store.recover_journal(home)
        for q in (home / "logs").glob(".store.journal.corrupt.*.json"):
            q.unlink()

        assert ("open", "logs") in dir_events
        assert ("open", "tasks") in dir_events
        assert ("fsync", DIR_FD) in dir_events
        assert ("close", DIR_FD) in dir_events

        # Non-EINVAL/ENOTSUP directory fsync failure is surfaced and still closes the descriptor
        def failing_dir_fsync(fd):
            if fd == DIR_FD:
                raise OSError(errno.EIO, "simulated disk I/O error on directory fsync")
            return real_fsync(fd)

        monkeypatch.setattr(store.os, "fsync", failing_dir_fsync)
        with pytest.raises(OSError, match="simulated disk I/O error"):
            store._fsync_parent_dir(ledger_path)
    finally:
        monkeypatch.setattr(store, "_SUPPORTS_DIR_FSYNC", real_supports_dir_fsync)
        monkeypatch.setattr(store.os, "open", real_open)
        monkeypatch.setattr(store.os, "fsync", real_fsync)
        monkeypatch.setattr(store.os, "close", real_close)


def test_lock_exclusivity_live_pid_protection_and_token_checked_release(home, monkeypatch):
    import sys

    monkeypatch.setattr(store, "LOCK_STALE_SECONDS", 0.05)
    lock_path = home / "logs" / ".store.lock"

    # 1. Writer A holds the lock longer than LOCK_STALE_SECONDS while its PID is alive;
    #    Writer B and Writer C must NOT steal A's lock!
    entered = threading.Event()
    release_a = threading.Event()
    b_stolen = []

    def writer_a():
        with store.store_lock(home, timeout=1.0):
            entered.set()
            release_a.wait(timeout=1.0)

    t_a = threading.Thread(target=writer_a)
    t_a.start()
    assert entered.wait(timeout=1.0)
    time.sleep(0.08)  # Exceeds LOCK_STALE_SECONDS (0.05s), but owner holds OS + thread lock!

    for _ in range(2):
        with pytest.raises(TimeoutError):
            with store.store_lock(home, timeout=0.06):
                b_stolen.append(True)

    assert not b_stolen
    release_a.set()
    t_a.join()
    # Persistent lockfile is retained on disk so POSIX advisory locks never split across two inodes
    assert lock_path.exists()
    first_ino = lock_path.stat().st_ino

    # 2. Three-party handoff: Owner 1 releases, Process 2 acquires and holds the same persistent inode,
    #    and Contender 3 times out trying to enter while Process 2 holds it
    repo_root = str(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ready_file = home / "logs" / "p2_ready.flag"
    release_file = home / "logs" / "p2_release.flag"
    p2_code = (
        f"import pathlib, sys, time; sys.path.insert(0, {repo_root!r}); "
        f"from lifeos import store; "
        f"ready = pathlib.Path({str(ready_file)!r}); rel = pathlib.Path({str(release_file)!r}); "
        f"ctx = store.store_lock({str(home)!r}, timeout=2.0); ctx.__enter__(); "
        f"ready.write_text('1'); "
        f"deadline = time.time() + 3.0\n"
        f"while not rel.exists() and time.time() < deadline:\n"
        f"    time.sleep(0.01)\n"
        f"ctx.__exit__(None, None, None)"
    )
    p2 = subprocess.Popen([sys.executable, "-c", p2_code])
    try:
        deadline = time.time() + 3.0
        while not ready_file.exists() and time.time() < deadline:
            time.sleep(0.01)
        assert ready_file.exists()
        assert lock_path.stat().st_ino == first_ino
        with pytest.raises(TimeoutError):
            with store.store_lock(home, timeout=0.08):
                b_stolen.append(True)
        assert not b_stolen
    finally:
        release_file.write_text("1", encoding="ascii")
        assert p2.wait(timeout=5.0) == 0
        ready_file.unlink(missing_ok=True)
        release_file.unlink(missing_ok=True)

    # 3. Multiprocess dead-owner & two-contender recovery: a child process locks .store.lock and dies via os._exit(0);
    #    the OS immediately releases the advisory lock, and two contending subprocesses serialize cleanly without race
    crash_code = (
        f"import os, sys; sys.path.insert(0, {repo_root!r}); "
        f"from lifeos import store; "
        f"ctx = store.store_lock({str(home)!r}, timeout=2.0); ctx.__enter__(); os._exit(0)"
    )
    subprocess.run([sys.executable, "-c", crash_code], check=True)

    contend_code = (
        f"import sys, time; sys.path.insert(0, {repo_root!r}); "
        f"from lifeos import store; "
        f"rid = sys.argv[1]; "
        f"store.append_run_record({str(home)!r}, {{'run_id': rid, 'date': '2026-11-20', 'command': 'ask', 'status': 'ok'}})"
    )
    p1 = subprocess.Popen([sys.executable, "-c", contend_code, "R-261120-mp0001"])
    p2_mp = subprocess.Popen([sys.executable, "-c", contend_code, "R-261120-mp0002"])
    assert p1.wait(timeout=5.0) == 0
    assert p2_mp.wait(timeout=5.0) == 0
    mp_ids = {r["run_id"] for r in _read_runs(home)}
    assert {"R-261120-mp0001", "R-261120-mp0002"}.issubset(mp_ids)


def test_concurrent_writers_do_not_lose_or_corrupt_updates(home):
    task_path = home / "tasks" / "T-261116-demo-cli.md"
    ledger_path = home / "logs" / "ledger.csv"
    before_ledger_count = len(ledger_path.read_text(encoding="utf-8").splitlines())
    errors = []

    def worker(idx):
        try:
            rid = f"R-261120-conc{idx:04d}"
            rec = {
                "run_id": rid,
                "date": TODAY.isoformat(),
                "command": "ask",
                "task_id": "T-261116-demo-cli",
                "model": f"m{idx}",
                "status": "ok",
            }
            store.record_result(
                home, task_path, f"m{idx}", f"CONCURRENT ANSWER {idx}", TODAY,
                note="asked via lifeos ask; flags: 0", run_id=rid, run_record=rec,
            )
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    task_text = task_path.read_text(encoding="utf-8")
    ledger_lines = ledger_path.read_text(encoding="utf-8").splitlines()
    assert len(ledger_lines) == before_ledger_count + 8
    for i in range(8):
        assert f"CONCURRENT ANSWER {i}" in task_text
        assert any(f",T-261116-demo-cli,m{i},," in line for line in ledger_lines)
    runs = _read_runs(home)
    assert len(runs) == 8
    assert {r["run_id"] for r in runs} == {f"R-261120-conc{i:04d}" for i in range(8)}


def test_blocked_failed_timeout_tool_missing_partial_and_full_fail_runs_recorded_with_redaction(home, monkeypatch):
    leaked_secret = "ghp_" + "a1" * 18

    # 0. Outbound context blocked by guard -> status="blocked", phase="outbound_context"
    task_path = home / "tasks" / "T-261116-demo-cli.md"
    orig_task = task_path.read_text(encoding="utf-8")
    task_path.write_text(orig_task + f"\nkey {leaked_secret}\n", encoding="utf-8")
    with pytest.raises(ask.Blocked):
        ask.run_ask(home, "codex", "T-261116", adapters={"codex": lambda p: CLEAN}, today=TODAY, run_id="R-261120-blko0001")
    with pytest.raises(ask.Blocked):
        ask.run_review(home, "T-261116", reviewers=("codex",), adapters={"codex": lambda p: CLEAN}, today=TODAY, run_id="R-261120-blkr0001")
    task_path.write_text(orig_task, encoding="utf-8")

    # 0b. Provider-level privacy block (non-loopback OLLAMA_HOST) -> status="blocked", phase="provider_guard"
    monkeypatch.setenv("OLLAMA_HOST", "http://remote.example.org:11434")
    with pytest.raises(ask.Blocked):
        ask.run_ask(home, "ollama", "T-261116", today=TODAY, run_id="R-261120-blkp0001")
    monkeypatch.delenv("OLLAMA_HOST", raising=False)

    # 1. Provider timeout -> status="timeout"
    def timeout_adapter(prompt):
        raise ask.AskError("codex timed out after 600 s.")

    with pytest.raises(ask.AskError):
        ask.run_ask(home, "codex", "T-261116", adapters={"codex": timeout_adapter}, today=TODAY, run_id="R-261120-time0001")

    # 2. Provider failure containing a secret in stderr -> status="failed", secret redacted
    def failing_secret_adapter(prompt):
        raise ask.AskError(f"fatal: auth failed for {leaked_secret}")

    with pytest.raises(ask.AskError):
        ask.run_ask(home, "codex", "T-261116", adapters={"codex": failing_secret_adapter}, today=TODAY, run_id="R-261120-fail0001")

    # 2b. Unexpected RuntimeError / CalledProcessError inside adapter -> status="failed", wrapped as AskError
    def unexpected_crash_adapter(prompt):
        raise RuntimeError(f"unexpected adapter crash with {leaked_secret}")

    with pytest.raises(ask.AskError):
        ask.run_ask(home, "codex", "T-261116", adapters={"codex": unexpected_crash_adapter}, today=TODAY, run_id="R-261120-unex0001")

    # 3. Missing tool -> status="tool_missing"
    def missing_adapter(prompt):
        raise ask.ToolMissing("codex is not installed or not on PATH.")

    with pytest.raises(ask.ToolMissing):
        ask.run_ask(home, "codex", "T-261116", adapters={"codex": missing_adapter}, today=TODAY, run_id="R-261120-miss0001")

    # 4. Inbound answer blocked by guard -> status="blocked", phase="inbound_answer"
    def leaky_answer_adapter(prompt):
        return "key " + leaked_secret

    with pytest.raises(ask.Blocked):
        ask.run_ask(home, "codex", "T-261116", adapters={"codex": leaky_answer_adapter}, today=TODAY, run_id="R-261120-blka0001")

    # 5. Partial multi-model review (one succeeds, one raises unexpected RuntimeError) -> parent status="partial"
    with pytest.raises(ask.AskError):
        ask.run_review(
            home, "T-261116", reviewers=("codex", "claude"),
            adapters={"codex": lambda p: CLEAN, "claude": unexpected_crash_adapter},
            today=TODAY, run_id="R-261120-partgrp1",
        )

    # 6. Fully failed multi-model review (all reviewers fail) -> parent status="failed"
    with pytest.raises(ask.AskError):
        ask.run_review(
            home, "T-261116", reviewers=("codex", "claude"),
            adapters={"codex": failing_secret_adapter, "claude": timeout_adapter},
            today=TODAY, run_id="R-261120-failgrp1",
        )

    raw_runs = (home / "logs" / "runs.jsonl").read_text(encoding="utf-8")
    assert leaked_secret not in raw_runs  # Secret never enters runs.jsonl!
    by_id = {r["run_id"]: r for r in _read_runs(home)}
    assert by_id["R-261120-blko0001"]["status"] == "blocked" and by_id["R-261120-blko0001"]["phase"] == "outbound_context"
    assert by_id["R-261120-blkr0001"]["status"] == "blocked" and by_id["R-261120-blkr0001"]["phase"] == "outbound_context"
    assert by_id["R-261120-blkp0001"]["status"] == "blocked" and by_id["R-261120-blkp0001"]["phase"] == "provider_guard"
    assert by_id["R-261120-time0001"]["status"] == "timeout"
    assert by_id["R-261120-fail0001"]["status"] == "failed"
    assert "[REDACTED]" in by_id["R-261120-fail0001"]["error"]
    assert by_id["R-261120-unex0001"]["status"] == "failed"
    assert "[REDACTED]" in by_id["R-261120-unex0001"]["error"]
    assert by_id["R-261120-miss0001"]["status"] == "tool_missing"
    assert by_id["R-261120-blka0001"]["status"] == "blocked" and by_id["R-261120-blka0001"]["phase"] == "inbound_answer"
    assert by_id["R-261120-partgrp1"]["command"] == "review_group" and by_id["R-261120-partgrp1"]["status"] == "partial"
    assert by_id["R-261120-failgrp1"]["command"] == "review_group" and by_id["R-261120-failgrp1"]["status"] == "failed"

    # 7. Retrying any persisted failed/blocked/timeout/tool_missing/partial run_id replays the failure
    #    (both Python API and CLI exit codes 1/2/3) without calling the adapter again or adding run records
    run_count_before = len(_read_runs(home))
    retry_calls = []

    def never_called_adapter(prompt):
        retry_calls.append(prompt)
        return CLEAN

    for blkid in ("R-261120-blko0001", "R-261120-blka0001"):
        with pytest.raises(ask.Blocked):
            ask.run_ask(home, "codex", "T-261116", adapters={"codex": never_called_adapter}, today=TODAY, run_id=blkid)
        assert cli.main(["--home", str(home), "ask", "codex", "T-261116", "--run-id", blkid]) == 1

    with pytest.raises(ask.Blocked):
        ask.run_ask(home, "ollama", "T-261116", adapters={"ollama": never_called_adapter}, today=TODAY, run_id="R-261120-blkp0001")
    assert cli.main(["--home", str(home), "ask", "ollama", "T-261116", "--run-id", "R-261120-blkp0001"]) == 1

    with pytest.raises(ask.ToolMissing):
        ask.run_ask(home, "codex", "T-261116", adapters={"codex": never_called_adapter}, today=TODAY, run_id="R-261120-miss0001")
    assert cli.main(["--home", str(home), "ask", "codex", "T-261116", "--run-id", "R-261120-miss0001"]) == 2

    for errid in ("R-261120-time0001", "R-261120-fail0001", "R-261120-unex0001"):
        with pytest.raises(ask.AskError):
            ask.run_ask(home, "codex", "T-261116", adapters={"codex": never_called_adapter}, today=TODAY, run_id=errid)
        assert cli.main(["--home", str(home), "ask", "codex", "T-261116", "--run-id", errid]) == 3

    with pytest.raises(ask.Blocked):
        ask.run_review(home, "T-261116", reviewers=("codex",), adapters={"codex": never_called_adapter}, today=TODAY, run_id="R-261120-blkr0001")
    assert cli.main(["--home", str(home), "review", "T-261116", "--reviewers", "codex", "--run-id", "R-261120-blkr0001"]) == 1

    for grpid in ("R-261120-partgrp1", "R-261120-failgrp1"):
        with pytest.raises(ask.AskError):
            ask.run_review(home, "T-261116", reviewers=("codex", "claude"), adapters={"codex": never_called_adapter, "claude": never_called_adapter}, today=TODAY, run_id=grpid)
        assert cli.main(["--home", str(home), "review", "T-261116", "--reviewers", "codex,claude", "--run-id", grpid]) == 3

    assert not retry_calls
    assert len(_read_runs(home)) == run_count_before


def test_full_64_char_sha256_and_per_reviewer_isolated_worktree_review(home, tmp_path):
    assert len(context.pack_hash("hello world")) == 64

    repo = tmp_path / "sample-repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.org"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)
    orig_code = "def add(a, b):\n    return a + b\n"
    (repo / "module.py").write_text(orig_code, encoding="utf-8")
    subprocess.run(["git", "add", "module.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Add module.py"], cwd=repo, check=True, capture_output=True)
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()

    observed = {"cwds": [], "r2_module_text": None}

    def mutating_reviewer_1(prompt):
        cwd = ask.current_review_cwd()
        observed["cwds"].append(cwd)
        # Attempt to poison the worktree for later reviewers
        (cwd / "module.py").write_text("MUTATED BY REVIEWER 1\n", encoding="utf-8")
        (cwd / "untracked.txt").write_text("POISON\n", encoding="utf-8")
        return CLEAN

    def verifying_reviewer_2(prompt):
        cwd = ask.current_review_cwd()
        observed["cwds"].append(cwd)
        observed["r2_module_text"] = (cwd / "module.py").read_text(encoding="utf-8")
        observed["r2_has_untracked"] = (cwd / "untracked.txt").exists()
        observed["prompt"] = prompt
        return CLEAN

    out = ask.run_review(
        home, "T-261116", reviewers=("r1", "r2"),
        adapters={"r1": mutating_reviewer_1, "r2": verifying_reviewer_2},
        today=TODAY, repo=repo, commit="HEAD", run_id="R-261120-wtgroup1",
    )
    # Reviewer 2 got its own fresh isolated worktree, completely unaffected by Reviewer 1's mutation!
    assert len(observed["cwds"]) == 2 and observed["cwds"][0] != observed["cwds"][1]
    assert observed["r2_module_text"] == orig_code
    assert observed["r2_has_untracked"] is False
    assert out["commit_sha"] == head_sha
    assert head_sha in observed["prompt"]

    # Both temporary detached worktrees were cleaned up after review finished
    wt_list = subprocess.run(
        ["git", "worktree", "list"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip().splitlines()
    assert len(wt_list) == 1

    by_id = {r["run_id"]: r for r in _read_runs(home)}
    parent = by_id["R-261120-wtgroup1"]
    assert parent["command"] == "review_group" and parent["status"] == "ok" and parent["commit_sha"] == head_sha
    for cid in parent["child_run_ids"]:
        assert by_id[cid]["commit_sha"] == head_sha

    # Record a failed repository review as well before mutating/deleting the repo
    with pytest.raises(ask.AskError):
        ask.run_review(
            home, "T-261116", reviewers=("r1",),
            adapters={"r1": lambda p: (_ for _ in ()).throw(RuntimeError("worktree reviewer boom"))},
            today=TODAY, repo=repo, commit="HEAD", run_id="R-261120-wtfail01",
        )

    # Record an initial repository inspection failure (invalid commit ref -> commit_sha is None, requested_commit="bad-ref"):
    # retrying with the SAME requested_commit replays AskError, while reusing the run_id with a different commit raises ValueError!
    with pytest.raises(ask.AskError):
        ask.run_review(
            home, "T-261116", reviewers=("r1",),
            adapters={"r1": verifying_reviewer_2},
            today=TODAY, repo=repo, commit="bad-ref-does-not-exist", run_id="R-261120-wtinspfail",
        )
    with pytest.raises(ask.AskError):
        ask.run_review(
            home, "T-261116", reviewers=("r1",),
            adapters={"r1": verifying_reviewer_2},
            today=TODAY, repo=repo, commit="bad-ref-does-not-exist", run_id="R-261120-wtinspfail",
        )
    with pytest.raises(ValueError, match="already belongs to commit"):
        ask.run_review(
            home, "T-261116", reviewers=("r1",),
            adapters={"r1": verifying_reviewer_2},
            today=TODAY, repo=repo, commit="HEAD", run_id="R-261120-wtinspfail",
        )

    # Constrained-budget review pack: even when task facts and rules.md are huge, repo_commit and commit_diff are guaranteed
    # and the returned token estimate never exceeds budget (at 80 and 250 tokens).
    repo_info_for_budget = context.inspect_repo_commit(repo, "HEAD")
    big_task = home / "tasks" / "T-261120-bigreview.md"
    big_task.write_text("# Big Task\n" + ("detailed context line " * 400) + "\n", encoding="utf-8")
    constrained_pack, constrained_tokens = context.build_review_pack(
        home, "T-261120-bigreview", budget=250, repo_info=repo_info_for_budget
    )
    assert f"=== repo_commit ({head_sha[:12]})" in constrained_pack
    assert f"=== commit_diff ({head_sha[:12]})" in constrained_pack
    assert "def add(a, b):" in constrained_pack
    assert constrained_tokens <= 250
    pack_80, tokens_80 = context.build_review_pack(
        home, "T-261120-bigreview", budget=80, repo_info=repo_info_for_budget
    )
    assert f"=== repo_commit ({head_sha[:12]})" in pack_80
    assert f"=== commit_diff ({head_sha[:12]})" in pack_80
    assert tokens_80 <= 80
    with pytest.raises(ValueError, match="too small to include repository metadata and commit diff"):
        context.build_review_pack(home, "T-261120-bigreview", budget=40, repo_info=repo_info_for_budget)
    with pytest.raises(ValueError, match="too small to include repository metadata and commit diff"):
        context.build_review_pack(home, "T-261120-bigreview", budget=70, repo_info=repo_info_for_budget)

    # Partial-review crash recovery rejects reusing child 1 if HEAD advances before retry or if child lacks requested_commit!
    class SimulatedRepoCrash(BaseException):
        pass

    wt_crash_calls = []

    def r2_wt_crash(prompt):
        wt_crash_calls.append(prompt)
        if len(wt_crash_calls) == 1:
            raise SimulatedRepoCrash("crash after child 1 in worktree review")
        return CLEAN

    with pytest.raises(SimulatedRepoCrash):
        ask.run_review(
            home, "T-261116", reviewers=("r1", "r2"),
            adapters={"r1": verifying_reviewer_2, "r2": r2_wt_crash},
            today=TODAY, repo=repo, commit="HEAD", run_id="R-261120-wtcrashsha",
        )
    # Also test a legacy/incomplete child record lacking requested_commit during parentless crash recovery
    runs_file = home / "logs" / "runs.jsonl"
    legacy_child = dict(store.get_run_record(home, "R-261120-wtcrashsha-c1"))
    legacy_child["run_id"] = "R-261120-wtcrashnoreq-c1"
    legacy_child["parent_run_id"] = "R-261120-wtcrashnoreq"
    legacy_child.pop("requested_commit", None)
    with open(runs_file, "a", encoding="utf-8") as rf:
        rf.write(json.dumps(legacy_child) + "\n")
    with pytest.raises(ValueError, match="already belongs to a different context or commit"):
        ask.run_review(
            home, "T-261116", reviewers=("r1", "r2"),
            adapters={"r1": verifying_reviewer_2, "r2": verifying_reviewer_2},
            today=TODAY, repo=repo, commit="HEAD", run_id="R-261120-wtcrashnoreq",
        )

    # Create a feature branch and merge commit (--no-ff): inspect_repo_commit must produce a non-empty first-parent diff!
    default_branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    subprocess.run(["git", "checkout", "-b", "feat-merge-diff"], cwd=repo, check=True, capture_output=True)
    (repo / "module.py").write_text(orig_code + "\ndef sub(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "add", "module.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Add sub helper"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "checkout", default_branch], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "merge", "--no-ff", "feat-merge-diff", "-m", "Merge feat-merge-diff"], cwd=repo, check=True, capture_output=True)
    merge_info = context.inspect_repo_commit(repo, "HEAD")
    assert "def sub(a, b):" in merge_info["diff_text"]

    with pytest.raises(ValueError, match="already belongs to a different context or commit"):
        ask.run_review(
            home, "T-261116", reviewers=("r1", "r2"),
            adapters={"r1": verifying_reviewer_2, "r2": r2_wt_crash},
            today=TODAY, repo=repo, commit="HEAD", run_id="R-261120-wtcrashsha",
        )

    # Reusing a completed parent run_id with a different requested commit string (includingHEAD vs resolved SHA) is rejected
    with pytest.raises(ValueError, match="already belongs to commit"):
        ask.run_review(
            home, "T-261116", reviewers=("r1", "r2"),
            adapters={"r1": mutating_reviewer_1, "r2": verifying_reviewer_2},
            today=TODAY, repo=repo, commit="HEAD~1", run_id="R-261120-wtgroup1",
        )
    with pytest.raises(ValueError, match="already belongs to commit"):
        ask.run_review(
            home, "T-261116", reviewers=("r1", "r2"),
            adapters={"r1": mutating_reviewer_1, "r2": verifying_reviewer_2},
            today=TODAY, repo=repo, commit=head_sha, run_id="R-261120-wtgroup1",
        )

    # Corrupt the existing repository on disk so any git inspection would fail: persisted parent runs still replay
    # without inspecting git!
    (repo / ".git" / "HEAD").write_text("corrupted-invalid-git-head\n", encoding="utf-8")
    replay_broken_ok = ask.run_review(
        home, "T-261116", reviewers=("r1", "r2"),
        adapters={"r1": mutating_reviewer_1, "r2": verifying_reviewer_2},
        today=TODAY, repo=repo, commit="HEAD", run_id="R-261120-wtgroup1",
    )
    assert replay_broken_ok["commit_sha"] == head_sha and replay_broken_ok["group_run_id"] == "R-261120-wtgroup1"
    with pytest.raises(ask.AskError, match="worktree reviewer boom"):
        ask.run_review(
            home, "T-261116", reviewers=("r1",),
            adapters={"r1": verifying_reviewer_2},
            today=TODAY, repo=repo, commit="HEAD", run_id="R-261120-wtfail01",
        )

    # Remove/relocate the reviewed repository from its path completely: retrying with the original run_id still replays
    # both the persisted ok metadata and the persisted failure without reopening the repository!
    shutil.move(str(repo), str(tmp_path / "relocated-sample-repo"))
    assert not repo.exists()
    replay_ok = ask.run_review(
        home, "T-261116", reviewers=("r1", "r2"),
        adapters={"r1": mutating_reviewer_1, "r2": verifying_reviewer_2},
        today=TODAY, repo=repo, commit="HEAD", run_id="R-261120-wtgroup1",
    )
    assert replay_ok["commit_sha"] == head_sha and replay_ok["group_run_id"] == "R-261120-wtgroup1"
    with pytest.raises(ask.AskError, match="worktree reviewer boom"):
        ask.run_review(
            home, "T-261116", reviewers=("r1",),
            adapters={"r1": verifying_reviewer_2},
            today=TODAY, repo=repo, commit="HEAD", run_id="R-261120-wtfail01",
        )


def test_doctor_tools_and_live_cli_exit_codes(home, monkeypatch, capsys):
    # All healthy -> cli.main exits 0
    class AllTagsResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"models": [{"name": "qwen2.5:3b"}, {"name": "llama3.2"}]}'

    class VersionOk:
        returncode, stdout, stderr = 0, "1.0.0\n", ""

    monkeypatch.setattr(ask, "_open_local", lambda req, timeout: AllTagsResp())
    monkeypatch.setattr(ask.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(ask.subprocess, "run", lambda *a, **kw: VersionOk())
    monkeypatch.delenv("LIFEOS_OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("LIFEOS_QWEN_MODEL", raising=False)

    assert cli.main(["--home", str(home), "doctor", "--tools", "--live"]) == 0
    out_ok = capsys.readouterr().out
    assert "healthy" in out_ok and "cli_healthy" in out_ok and "doctor: ok" in out_ok

    # Authenticated --smoke probe invokes every configured provider adapter (both local and remote)
    smoke_called = []

    def make_smoke(name):
        def _smoke(prompt):
            smoke_called.append(name)
            return "OK"
        return _smoke

    monkeypatch.setattr(ask, "ADAPTERS", {k: make_smoke(k) for k in ask.PROVIDERS})
    assert cli.main(["--home", str(home), "doctor", "--smoke"]) == 0
    out_smoke = capsys.readouterr().out
    assert set(smoke_called) == set(ask.PROVIDERS)
    assert "smoke ok" in out_smoke and "doctor: ok" in out_smoke

    # Missing model in Ollama -> cli.main exits 1 and reports problems to fix
    class PartialTagsResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"models": [{"name": "qwen2.5:3b"}]}'

    monkeypatch.setattr(ask, "_open_local", lambda req, timeout: PartialTagsResp())
    assert cli.main(["--home", str(home), "doctor", "--tools", "--live"]) == 1
    out_bad = capsys.readouterr().out
    assert "model_missing" in out_bad and "doctor: 1 thing(s) to fix" in out_bad

    # Missing CLI binary with --tools -> cli.main exits 1
    monkeypatch.setattr(ask.shutil, "which", lambda name: None if name == "codex" else f"/usr/bin/{name}")
    assert cli.main(["--home", str(home), "doctor", "--tools"]) == 1
    out_miss = capsys.readouterr().out
    assert "missing" in out_miss and "doctor: 1 thing(s) to fix" in out_miss


def test_schema_versioning_v1_normalization_and_locked_proof_logging(home):
    # 1. Legacy v1 records (both 12-char hash and schema-less 64-char hash) + v2 record coexist cleanly
    runs_path = home / "logs" / "runs.jsonl"
    v1_legacy_12 = {
        "run_id": "R-261113-legacy01",
        "date": "2026-11-13",
        "command": "ask",
        "task_id": "T-261116-demo-cli",
        "model": "qwen:qwen2.5:3b",
        "context_sha256": "abcdef012345",
        "status": "ok",
    }
    v1_legacy_64 = {
        "run_id": "R-261113-legacy64",
        "date": "2026-11-13",
        "command": "ask",
        "task_id": "T-261116-demo-cli",
        "model": "codex",
        "context_sha256": "a" * 64,
        "status": "ok",
    }
    runs_path.write_text(json.dumps(v1_legacy_12) + "\n" + json.dumps(v1_legacy_64) + "\n", encoding="utf-8")

    # Newly written records always force schema_version=2 even if caller passes schema_version=1
    store.append_run_record(home, {
        "schema_version": 1,
        "run_id": "R-261120-forcedv2",
        "date": TODAY.isoformat(),
        "command": "ask",
        "task_id": "T-261116-demo-cli",
        "model": "fake",
        "context_sha256": "b" * 64,
        "status": "ok",
    })
    ask.run_ask(
        home, "fake", "T-261116", adapters={"fake": lambda p: CLEAN}, today=TODAY, run_id="R-261120-v2rec001"
    )
    records = {r["run_id"]: r for r in store.read_run_records(home, normalize=True)}
    assert records["R-261113-legacy01"]["schema_version"] == 1
    assert records["R-261113-legacy01"]["hash_format"] == "sha256_prefix_12"
    assert records["R-261113-legacy01"]["started_at"] == "2026-11-13T00:00:00Z"
    assert records["R-261113-legacy01"]["terminal"] is True

    # Schema-less 64-char historical record is still schema_version == 1 with hash_format == "sha256_64"
    assert records["R-261113-legacy64"]["schema_version"] == 1
    assert records["R-261113-legacy64"]["hash_format"] == "sha256_64"
    assert records["R-261113-legacy64"]["terminal"] is True

    assert records["R-261120-forcedv2"]["schema_version"] == 2
    v2 = records["R-261120-v2rec001"]
    assert v2["schema_version"] == 2
    assert v2["hash_format"] == "sha256_64"
    assert v2["started_at"].endswith("Z") and v2["finished_at"].endswith("Z")
    assert v2["terminal"] is True

    # Non-terminal or unknown status is rejected before writing
    with pytest.raises(ValueError, match="Invalid non-terminal run status"):
        store.append_run_record(home, {"run_id": "R-bad", "status": "running"})

    # 2. Concurrent append_proof_row calls under store_lock neither duplicate identical tokens nor lose distinct rows
    proofs_path = home / "logs" / "proofs.csv"
    before_rows = len(proofs_path.read_text(encoding="utf-8").splitlines())
    results = []

    def proof_worker(idx):
        # All 4 even threads race on the exact same dedupe_token; 4 odd threads write distinct tokens
        token = "results shared_hash" if idx % 2 == 0 else f"results unique_{idx}"
        wrote = store.append_proof_row(
            proofs_path, "2026-11-20", "lab", f"demo v1; 5/5; {token}", "logs/lab/demo.md",
            dedupe_token=token, home=home,
        )
        results.append((idx, wrote))

    threads = [threading.Thread(target=proof_worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    even_writes = [w for idx, w in results if idx % 2 == 0]
    odd_writes = [w for idx, w in results if idx % 2 == 1]
    assert sum(even_writes) == 1  # Exactly 1 of the 4 racing threads wrote the shared dedupe_token
    assert sum(odd_writes) == 4   # All 4 distinct tokens were preserved without lost updates
    after_rows = len(proofs_path.read_text(encoding="utf-8").splitlines())
    assert after_rows == before_rows + 5
