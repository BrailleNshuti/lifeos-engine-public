"""Durable writes shared by LifeOS commands.

All task results, ledger rows and execution run records pass through this
module so atomic writes, idempotency, quoting, line boundaries and the
model-call contract cannot drift between features.
"""
import csv
import datetime as dt
import io
import json
import os
import re
import uuid
from pathlib import Path

ASK_NOTE_PREFIX = "asked via lifeos ask"
FLAGS_LABEL = "flags"


def _atomic_write_bytes(path, data):
    """Write bytes to a sibling temp file and atomically replace the target."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


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


def append_task_result(path, model, text, today):
    """Atomically append a result block to a task file."""
    path = Path(path)
    block = f"\n## Result · {model} · {today:%Y-%m-%d}\n{text}\n"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    _atomic_write_bytes(path, (existing + block).encode("utf-8"))
    return True


def append_ledger_row(ledger, today, task_id, model, note):
    """Atomically append one valid CSV row, repairing a missing final newline first."""
    ledger = Path(ledger)
    if not ledger.exists():
        return
    raw = ledger.read_bytes()
    if raw and raw[-1:] not in (b"\n", b"\r"):
        raw += b"\n"
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerow(
        [today.isoformat(), task_id, model, "", note]
    )
    _atomic_write_bytes(ledger, raw + buf.getvalue().encode("utf-8"))


def has_run_id(home, run_id):
    """Return True if a run_id is already recorded in logs/runs.jsonl."""
    if not run_id:
        return False
    runs = Path(home) / "logs" / "runs.jsonl"
    if not runs.exists():
        return False
    for line in runs.read_text(encoding="utf-8").splitlines():
        if line.strip() and json.loads(line).get("run_id") == run_id:
            return True
    return False


def append_run_record(home, record):
    """Atomically append one immutable JSONL run record to logs/runs.jsonl if logs/ exists."""
    logs = Path(home) / "logs"
    if not logs.is_dir():
        return None
    if has_run_id(home, record.get("run_id")):
        return logs / "runs.jsonl"
    runs = logs / "runs.jsonl"
    raw = runs.read_bytes() if runs.exists() else b""
    if raw and raw[-1:] not in (b"\n", b"\r"):
        raw += b"\n"
    line = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
    _atomic_write_bytes(runs, raw + line)
    return runs


def record_result(home, path, model, text, today, note="written via lifeos mcp", run_id=None):
    if has_run_id(home, run_id):
        return False
    append_task_result(path, model, text, today)
    append_ledger_row(Path(home) / "logs" / "ledger.csv", today, Path(path).stem, model, note)
    return True

