"""Parallel writers (threads and separate processes) must neither lose a record nor break the hash chain."""
import json
import subprocess
import sys
import threading
from pathlib import Path

from lifeos import store, verify

ROOT = Path(__file__).resolve().parent.parent


def rec(i, tag="t"):
    return {"run_id": f"R-{tag}-{i:04d}", "command": "canary", "status": "ok", "model": "claude", "date": "2026-11-18"}


def test_threads_append_without_losing_or_breaking_the_chain(tmp_path):
    (tmp_path / "logs").mkdir()
    threads = [threading.Thread(target=lambda n=n: [store.append_run_record(tmp_path, rec(n * 10 + i)) for i in range(10)])
               for n in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    res = verify.verify_chain(tmp_path)
    assert res["ok"] and res["records"] == 80, res
    ids = [json.loads(line)["run_id"] for line in (tmp_path / "logs" / "runs.jsonl").read_text().splitlines()]
    assert len(set(ids)) == 80


def test_processes_append_without_losing_or_breaking_the_chain(tmp_path):
    (tmp_path / "logs").mkdir()
    code = ("import sys; from lifeos import store; "
            "n=sys.argv[2]; [store.append_run_record(sys.argv[1], {'run_id': f'R-{n}-{i:04d}', 'command': 'canary', "
            "'status': 'ok', 'model': 'claude', 'date': '2026-11-18'}) for i in range(10)]")
    procs = [subprocess.Popen([sys.executable, "-c", code, str(tmp_path), str(n)], cwd=ROOT) for n in range(5)]
    assert [p.wait(timeout=60) for p in procs] == [0] * 5
    res = verify.verify_chain(tmp_path)
    assert res["ok"] and res["records"] == 50, res


def test_a_repeated_run_id_is_written_once(tmp_path):
    (tmp_path / "logs").mkdir()
    for _ in range(3):
        store.append_run_record(tmp_path, rec(1))
    assert verify.verify_chain(tmp_path)["records"] == 1
