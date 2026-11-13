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


def test_pre_execution_run_id_idempotency_prevents_duplicate_ask_and_review(home):
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
    r1_calls = []
    r2_calls = []

    def r1_ok(prompt):
        r1_calls.append(prompt)
        return CLEAN

    def r2_crash_once(prompt):
        r2_calls.append(prompt)
        if len(r2_calls) == 1:
            raise RuntimeError("simulated uncatchable process crash after child 1 committed")
        return CLEAN

    with pytest.raises(RuntimeError, match="simulated uncatchable process crash"):
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
    assert not lock_path.exists()

    # 2. Multiprocess dead-owner & two-contender recovery: a child process locks .store.lock and dies via os._exit(0);
    #    the OS immediately releases the advisory lock, and two contending subprocesses serialize cleanly without race
    repo_root = str(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
    p2 = subprocess.Popen([sys.executable, "-c", contend_code, "R-261120-mp0002"])
    assert p1.wait(timeout=5.0) == 0
    assert p2.wait(timeout=5.0) == 0
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
        ask.run_ask(home, "fake", "T-261116", adapters={"fake": lambda p: CLEAN}, today=TODAY, run_id="R-261120-blko0001")
    with pytest.raises(ask.Blocked):
        ask.run_review(home, "T-261116", reviewers=("fake",), adapters={"fake": lambda p: CLEAN}, today=TODAY, run_id="R-261120-blkr0001")
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
        ask.run_ask(home, "fake", "T-261116", adapters={"fake": timeout_adapter}, today=TODAY, run_id="R-261120-time0001")

    # 2. Provider failure containing a secret in stderr -> status="failed", secret redacted
    def failing_secret_adapter(prompt):
        raise ask.AskError(f"fatal: auth failed for {leaked_secret}")

    with pytest.raises(ask.AskError):
        ask.run_ask(home, "fake", "T-261116", adapters={"fake": failing_secret_adapter}, today=TODAY, run_id="R-261120-fail0001")

    # 3. Missing tool -> status="tool_missing"
    def missing_adapter(prompt):
        raise ask.ToolMissing("codex is not installed or not on PATH.")

    with pytest.raises(ask.ToolMissing):
        ask.run_ask(home, "fake", "T-261116", adapters={"fake": missing_adapter}, today=TODAY, run_id="R-261120-miss0001")

    # 4. Inbound answer blocked by guard -> status="blocked", phase="inbound_answer"
    def leaky_answer_adapter(prompt):
        return "key " + leaked_secret

    with pytest.raises(ask.Blocked):
        ask.run_ask(home, "fake", "T-261116", adapters={"fake": leaky_answer_adapter}, today=TODAY, run_id="R-261120-blka0001")

    # 5. Partial multi-model review (one succeeds, one fails) -> parent status="partial"
    with pytest.raises(ask.AskError):
        ask.run_review(
            home, "T-261116", reviewers=("ok_rev", "bad_rev"),
            adapters={"ok_rev": lambda p: CLEAN, "bad_rev": failing_secret_adapter},
            today=TODAY, run_id="R-261120-partgrp1",
        )

    # 6. Fully failed multi-model review (all reviewers fail) -> parent status="failed"
    with pytest.raises(ask.AskError):
        ask.run_review(
            home, "T-261116", reviewers=("bad1", "bad2"),
            adapters={"bad1": failing_secret_adapter, "bad2": timeout_adapter},
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
    assert by_id["R-261120-miss0001"]["status"] == "tool_missing"
    assert by_id["R-261120-blka0001"]["status"] == "blocked" and by_id["R-261120-blka0001"]["phase"] == "inbound_answer"
    assert by_id["R-261120-partgrp1"]["command"] == "review_group" and by_id["R-261120-partgrp1"]["status"] == "partial"
    assert by_id["R-261120-failgrp1"]["command"] == "review_group" and by_id["R-261120-failgrp1"]["status"] == "failed"


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
