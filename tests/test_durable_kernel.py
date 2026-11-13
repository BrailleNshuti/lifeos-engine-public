"""Tests for Execution Kernel Durable: pre-execution run_id idempotency, transactional journal recovery,
exclusive file locking under concurrent writers, failed/blocked/timeout/partial run logging with redaction,
64-char SHA-256 digests, real provider health probes, and isolated git worktree + commit diff blind reviews."""
import datetime as dt
import json
import shutil
import subprocess
import threading
import pytest

from lifeos import ask, context, store

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
    calls = []

    def counting_adapter(prompt):
        calls.append(prompt)
        return CLEAN

    task_path = home / "tasks" / "T-261116-demo-cli.md"
    before_task = task_path.read_text(encoding="utf-8")
    before_ledger = (home / "logs" / "ledger.csv").read_text(encoding="utf-8").splitlines()

    # First execution with explicit run_id
    ask.run_ask(
        home, "fake", "T-261116", adapters={"fake": counting_adapter}, today=TODAY, run_id="R-261120-idem0001"
    )
    assert len(calls) == 1
    after_first_task = task_path.read_text(encoding="utf-8")
    assert after_first_task != before_task

    # Retrying with the same run_id must NOT call the adapter again or duplicate task/ledger/run rows
    ask.run_ask(
        home, "fake", "T-261116", adapters={"fake": counting_adapter}, today=TODAY, run_id="R-261120-idem0001"
    )
    assert len(calls) == 1
    assert task_path.read_text(encoding="utf-8") == after_first_task
    assert len((home / "logs" / "ledger.csv").read_text(encoding="utf-8").splitlines()) == len(before_ledger) + 1
    runs = _read_runs(home)
    assert [r["run_id"] for r in runs] == ["R-261120-idem0001"]


def test_transactional_journal_recovers_partial_multi_file_crash(home, monkeypatch):
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

    # Journal file exists because transaction did not finish
    journal_path = home / "logs" / ".store.journal.json"
    assert journal_path.exists()

    # Restore os.replace and trigger recovery
    monkeypatch.setattr(store.os, "replace", real_replace)
    store.recover_journal(home)
    assert not journal_path.exists()
    assert "## Result · fake · 2026-11-20\n" + CLEAN in task_path.read_text(encoding="utf-8")
    assert "R-261120-crash001" in runs_path.read_text(encoding="utf-8")
    assert "T-261116-demo-cli,fake," in ledger_path.read_text(encoding="utf-8")

    # Retrying the same run_id after recovery is a no-op (no duplicate task/ledger/run rows)
    assert store.record_result(home, task_path, "fake", CLEAN, TODAY, note="asked via lifeos ask; flags: 0",
                               run_id="R-261120-crash001", run_record=rec) is False


def test_concurrent_writers_do_not_lose_or_corrupt_updates(home):
    task_path = home / "tasks" / "T-261116-demo-cli.md"
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
    for i in range(8):
        assert f"CONCURRENT ANSWER {i}" in task_text
    runs = _read_runs(home)
    assert len(runs) == 8
    assert {r["run_id"] for r in runs} == {f"R-261120-conc{i:04d}" for i in range(8)}


def test_blocked_failed_timeout_tool_missing_and_partial_runs_are_recorded_with_redaction(home):
    # 1. Provider timeout -> status="timeout"
    def timeout_adapter(prompt):
        raise ask.AskError("codex timed out after 600 s.")

    with pytest.raises(ask.AskError):
        ask.run_ask(home, "fake", "T-261116", adapters={"fake": timeout_adapter}, today=TODAY, run_id="R-261120-time0001")

    # 2. Provider failure containing a secret in stderr -> status="failed", secret redacted
    leaked_secret = "ghp_" + "a1" * 18

    def failing_secret_adapter(prompt):
        raise ask.AskError(f"fatal: auth failed for token {leaked_secret}")

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

    # 5. Partial multi-model review (one reviewer succeeds, second reviewer fails) -> parent recorded with status="partial"
    with pytest.raises(ask.AskError):
        ask.run_review(
            home, "T-261116", reviewers=("ok_rev", "bad_rev"),
            adapters={"ok_rev": lambda p: CLEAN, "bad_rev": failing_secret_adapter},
            today=TODAY, run_id="R-261120-partgrp1",
        )

    raw_runs = (home / "logs" / "runs.jsonl").read_text(encoding="utf-8")
    assert leaked_secret not in raw_runs  # Secret never enters runs.jsonl!
    by_id = {r["run_id"]: r for r in _read_runs(home)}
    assert by_id["R-261120-time0001"]["status"] == "timeout"
    assert by_id["R-261120-fail0001"]["status"] == "failed"
    assert "[REDACTED]" in by_id["R-261120-fail0001"]["error"]
    assert by_id["R-261120-miss0001"]["status"] == "tool_missing"
    assert by_id["R-261120-blka0001"]["status"] == "blocked"
    assert by_id["R-261120-partgrp1"]["command"] == "review_group"
    assert by_id["R-261120-partgrp1"]["status"] == "partial"
    assert len(by_id["R-261120-partgrp1"]["child_run_ids"]) == 2


def test_full_64_char_sha256_and_repo_worktree_commit_review(home, tmp_path):
    # Full 64-char SHA-256 digest
    assert len(context.pack_hash("hello world")) == 64

    # Create a real temporary Git repository with a commit to review
    repo = tmp_path / "sample-repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.org"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)
    (repo / "module.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    subprocess.run(["git", "add", "module.py"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Add module.py"], cwd=repo, check=True, capture_output=True)
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()

    observed = {}

    def worktree_checking_reviewer(prompt):
        observed["prompt"] = prompt
        observed["cwd"] = ask.current_review_cwd()
        if observed["cwd"]:
            observed["files"] = sorted(p.name for p in observed["cwd"].iterdir())
        return CLEAN

    out = ask.run_review(
        home, "T-261116", reviewers=("codex",), adapters={"codex": worktree_checking_reviewer},
        today=TODAY, repo=repo, commit="HEAD", run_id="R-261120-wtgroup1",
    )
    assert out["commit_sha"] == head_sha
    assert len(out["sha256"]) == 64
    assert head_sha in observed["prompt"]
    assert "def add(a, b):" in observed["prompt"]
    assert "module.py" in observed.get("files", [])

    # Temporary detached worktree was cleaned up after review finished
    wt_list = subprocess.run(
        ["git", "worktree", "list"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip().splitlines()
    assert len(wt_list) == 1

    # Parent and child records both exist and carry commit_sha
    by_id = {r["run_id"]: r for r in _read_runs(home)}
    parent = by_id["R-261120-wtgroup1"]
    assert parent["command"] == "review_group"
    assert parent["status"] == "ok"
    assert parent["commit_sha"] == head_sha
    child = by_id[parent["child_run_ids"][0]]
    assert child["parent_run_id"] == "R-261120-wtgroup1"
    assert child["commit_sha"] == head_sha


def test_provider_status_distinguishes_availability_from_live_health(monkeypatch):
    # Unprobed: reports binary availability, never claims live health
    rows = ask.provider_status(probe=False)
    assert all(r["status"] in ("available", "missing") for r in rows)
    assert all("capabilities" in r for r in rows)

    # Probed with mocked local Ollama /api/tags and CLI --version
    class TagsResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"models": [{"name": "qwen2.5:3b"}]}'

    class VersionDone:
        returncode, stdout, stderr = 0, "1.0.0\n", ""

    monkeypatch.setattr(ask, "_open_local", lambda req, timeout: TagsResp())
    monkeypatch.setattr(ask.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(ask.subprocess, "run", lambda *a, **kw: VersionDone())
    monkeypatch.delenv("LIFEOS_OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("LIFEOS_QWEN_MODEL", raising=False)

    probed = {r["model"]: r for r in ask.provider_status(probe=True)}
    assert probed["qwen"]["status"] == "healthy"
    assert probed["ollama"]["status"] == "model_missing"  # llama3.2 not in mocked /api/tags
    assert probed["codex"]["status"] == "healthy"
