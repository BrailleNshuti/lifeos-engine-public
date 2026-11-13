"""Durable writes shared by LifeOS commands.

All task results and ledger rows pass through this module so quoting, line
boundaries and the model-call contract cannot drift between features.
"""
import csv
import re
from pathlib import Path

ASK_NOTE_PREFIX = "asked via lifeos ask"
FLAGS_LABEL = "flags"


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
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"\n## Result · {model} · {today:%Y-%m-%d}\n{text}\n")


def append_ledger_row(ledger, today, task_id, model, note):
    """Append one valid CSV row, repairing a missing final newline first."""
    ledger = Path(ledger)
    if not ledger.exists():
        return
    if ledger.stat().st_size and ledger.read_bytes()[-1:] not in (b"\n", b"\r"):
        with open(ledger, "ab") as handle:
            handle.write(b"\n")
    with open(ledger, "a", encoding="utf-8", newline="") as handle:
        csv.writer(handle, lineterminator="\n").writerow(
            [today.isoformat(), task_id, model, "", note]
        )


def record_result(home, path, model, text, today, note="written via lifeos mcp"):
    append_task_result(path, model, text, today)
    append_ledger_row(Path(home) / "logs" / "ledger.csv", today, Path(path).stem, model, note)
