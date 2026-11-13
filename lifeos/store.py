"""Durable, locked, journaled writes shared by LifeOS commands.

All task results, ledger rows, proof rows and execution run records pass through
this module so exclusive file locking, write-ahead crash recovery, run_id
idempotency, CSV quoting, line boundaries and the model-call contract cannot
drift between features.
"""
import base64
from contextlib import contextmanager
import csv
import datetime as dt
import io
import json
import os
import re
import time
import uuid
from pathlib import Path

ASK_NOTE_PREFIX = "asked via lifeos ask"
FLAGS_LABEL = "flags"
LOCK_STALE_SECONDS = 30.0


def atomic_write_bytes(path, data):
    """Write bytes to a sibling temp file and atomically replace the target."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


_atomic_write_bytes = atomic_write_bytes


@contextmanager
def store_lock(home, timeout=10.0):
    """Acquire an exclusive cross-process/cross-thread lock on <home>/logs/.store.lock."""
    if home is None or not (Path(home) / "logs").is_dir():
        yield
        return
    lock_path = Path(home) / "logs" / ".store.lock"
    deadline = time.monotonic() + timeout
    fd = None
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, f"{os.getpid()}\n{time.time()}\n".encode("ascii"))
            finally:
                os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > LOCK_STALE_SECONDS:
                    lock_path.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for store lock: {lock_path}") from None
            time.sleep(0.01)
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def _journal_path(home):
    if home is None:
        return None
    logs = Path(home) / "logs"
    return logs / ".store.journal.json" if logs.is_dir() else None


def recover_journal(home):
    """Replay any uncommitted multi-file transaction left by an interrupted process."""
    jpath = _journal_path(home)
    if jpath is None or not jpath.exists():
        return False
    try:
        payload = json.loads(jpath.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        jpath.unlink(missing_ok=True)
        return False
    for entry in payload.get("operations", []):
        target = Path(entry["path"])
        data = base64.b64decode(entry["b64"])
        atomic_write_bytes(target, data)
    jpath.unlink(missing_ok=True)
    return True


def commit_transaction(home, operations):
    """Commit one or more (path, bytes) updates atomically via a write-ahead journal."""
    jpath = _journal_path(home)
    if jpath is not None and len(operations) > 1:
        journal_bytes = json.dumps(
            {
                "operations": [
                    {"path": str(Path(p)), "b64": base64.b64encode(data).decode("ascii")}
                    for p, data in operations
                ]
            },
            sort_keys=True,
        ).encode("utf-8")
        atomic_write_bytes(jpath, journal_bytes)
    for target, data in operations:
        atomic_write_bytes(Path(target), data)
    if jpath is not None and jpath.exists():
        jpath.unlink(missing_ok=True)


def new_run_id(today=None):
    """Return a unique, sortable run identifier (R-YYMMDD-xxxxxxxx)."""
    day = today or dt.date.today()
    return f"R-{day:%y%m%d}-{uuid.uuid4().hex[:8]}"


def model_call_note(flag_count):
    """Return the stable ledger note for one model call."""
    return f"{ASK_NOTE_PREFIX}; {FLAGS_LABEL}: {int(flag_count)}"


def model_call_flags(note):
    """Return the recorded flag count, or zero for old/malformed rows."""
    if not (note or "").strip().startswith(ASK_NOTE_PREFIX):
        return 0
    found = re.search(rf"{re.escape(FLAGS_LABEL)}:\s*(\d+)", note)
    return int(found.group(1)) if found else 0


def _prepare_task_result_bytes(path, model, text, today):
    path = Path(path)
    block = f"\n## Result · {model} · {today:%Y-%m-%d}\n{text}\n"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    return (existing + block).encode("utf-8")


def _prepare_csv_row_bytes(path, values):
    path = Path(path)
    raw = path.read_bytes()
    if raw and raw[-1:] not in (b"\n", b"\r"):
        raw += b"\n"
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerow(values)
    return raw + buf.getvalue().encode("utf-8")


def _prepare_run_record_bytes(runs_path, record):
    runs_path = Path(runs_path)
    raw = runs_path.read_bytes() if runs_path.exists() else b""
    if raw and raw[-1:] not in (b"\n", b"\r"):
        raw += b"\n"
    line = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
    return raw + line


def append_task_result(path, model, text, today):
    """Atomically append a result block to a task file."""
    path = Path(path)
    atomic_write_bytes(path, _prepare_task_result_bytes(path, model, text, today))
    return True


def append_csv_row(path, values):
    """Atomically append one valid CSV row, repairing a missing final newline first."""
    path = Path(path)
    if not path.exists():
        return False
    atomic_write_bytes(path, _prepare_csv_row_bytes(path, values))
    return True


def append_ledger_row(ledger, today, task_id, model, note):
    """Atomically append one valid CSV row, repairing a missing final newline first."""
    append_csv_row(ledger, [today.isoformat(), task_id, model, "", note])


def append_proof_row(proofs, date_str, area, proof, link, dedupe_token=None):
    """Atomically append one row to logs/proofs.csv unless dedupe_token is already present."""
    proofs = Path(proofs)
    if not proofs.exists():
        return False
    if dedupe_token and dedupe_token in proofs.read_text(encoding="utf-8"):
        return False
    return append_csv_row(proofs, [str(date_str), area, proof, str(link)])


def _has_run_id_unlocked(home, run_id):
    if not run_id or home is None:
        return False
    runs = Path(home) / "logs" / "runs.jsonl"
    if not runs.exists():
        return False
    for line in runs.read_text(encoding="utf-8").splitlines():
        if line.strip() and json.loads(line).get("run_id") == run_id:
            return True
    return False


def has_run_id(home, run_id):
    """Return True if a run_id is already recorded in logs/runs.jsonl (after replaying any uncommitted journal)."""
    if not run_id or home is None:
        return False
    with store_lock(home):
        recover_journal(home)
        return _has_run_id_unlocked(home, run_id)


def append_run_record(home, record):
    """Atomically append one immutable JSONL run record to logs/runs.jsonl if logs/ exists."""
    if home is None:
        return None
    logs = Path(home) / "logs"
    if not logs.is_dir():
        return None
    with store_lock(home):
        recover_journal(home)
        if _has_run_id_unlocked(home, record.get("run_id")):
            return logs / "runs.jsonl"
        runs = logs / "runs.jsonl"
        commit_transaction(home, [(runs, _prepare_run_record_bytes(runs, record))])
        return runs


def record_result(home, path, model, text, today, note="written via lifeos mcp", run_id=None, run_record=None):
    """Commit task result, ledger row and optional run record as one locked, journaled transaction."""
    path = Path(path)
    effective_id = run_id or (run_record.get("run_id") if isinstance(run_record, dict) else None)
    with store_lock(home):
        recover_journal(home)
        if _has_run_id_unlocked(home, effective_id):
            return False
        ops = [(path, _prepare_task_result_bytes(path, model, text, today))]
        if home is not None:
            ledger = Path(home) / "logs" / "ledger.csv"
            if ledger.exists():
                ops.append((ledger, _prepare_csv_row_bytes(ledger, [today.isoformat(), path.stem, model, "", note])))
            logs = Path(home) / "logs"
            if isinstance(run_record, dict) and logs.is_dir():
                runs = logs / "runs.jsonl"
                ops.append((runs, _prepare_run_record_bytes(runs, run_record)))
        commit_transaction(home, ops)
        return True
