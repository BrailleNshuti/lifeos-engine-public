"""lifeos log: append validated, guard-checked rows to proofs.csv, ledger.csv, health.csv, and hours.csv.

Every write uses exclusive store locking, UTF-8 without BOM, LF line endings, proper CSV quoting,
duplicate last-line refusal, range validation, and outbound privacy guard checks.
"""
import csv
import datetime as dt
import io
import math
from pathlib import Path

from .guard import private_patterns, scan_text
from .store import commit_transaction, recover_journal, store_lock

MAX_NOTE_CHARS = 200
VALID_HOURS_AREAS = ("german", "study", "lab", "work")
HEADERS = {
    "proofs.csv": ("date", "area", "proof", "link"),
    "ledger.csv": ("date", "task", "model", "minutes_saved", "note"),
    "health.csv": ("date", "sleep_h", "gym", "energy_1_5", "note"),
    "hours.csv": ("date", "area", "hours", "note"),
}


def _one_line(val):
    return " ".join(str(val or "").splitlines()).strip()


def _validate_date(date_val=None):
    if date_val is None:
        return dt.date.today().isoformat()
    if isinstance(date_val, dt.date) and not isinstance(date_val, dt.datetime):
        return date_val.isoformat()
    if not isinstance(date_val, str) or not date_val.strip():
        raise ValueError("Invalid date: expected YYYY-MM-DD.")
    raw = date_val.strip()
    try:
        return dt.date.fromisoformat(raw).isoformat()
    except ValueError:
        raise ValueError(f"Invalid date '{raw}': expected YYYY-MM-DD.") from None


def _check_guard(values):
    combined = "\n".join(str(v) for v in values if v)
    if not combined:
        return
    findings = scan_text(combined, private_patterns(), allow_mark=False)
    if findings:
        rules = ", ".join(sorted({f[2] for f in findings}))
        raise ValueError(f"Refused by privacy guard ({rules}).")


def _validate_note(note, label="note"):
    cleaned = _one_line(note)
    if len(cleaned) > MAX_NOTE_CHARS:
        raise ValueError(f"{label} is {len(cleaned)} characters (max {MAX_NOTE_CHARS}).")
    return cleaned


def _parse_float_range(val, name, low, high=None):
    if isinstance(val, bool):
        raise ValueError(f"Invalid {name}: boolean is not a number.")
    try:
        num = float(val)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid {name} '{val}': expected a number.") from None
    if not math.isfinite(num):
        raise ValueError(f"Invalid {name}: must be a finite number.")
    if num < low or (high is not None and num > high):
        bound = f"{low} to {high}" if high is not None else f">= {low}"
        raise ValueError(f"Invalid {name} {val}: must be in range {bound}.")
    return str(int(num)) if num.is_integer() else f"{num:g}"


def _format_csv_line(cols):
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerow(cols)
    return buf.getvalue().rstrip("\r\n")


def _append_csv_row(home, filename, cols):
    header_cols = HEADERS[filename]
    header_line = _format_csv_line(header_cols)
    new_line = _format_csv_line(cols)
    logs_dir = Path(home) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / filename

    with store_lock(home):
        recover_journal(home)
        existing_lines = []
        if path.exists():
            raw = path.read_bytes()
            text = raw.decode("utf-8-sig")
            existing_lines = [line for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if line]
        if not existing_lines:
            existing_lines = [header_line]
        elif existing_lines[0] != header_line:
            existing_lines = [header_line, *existing_lines]
        if len(existing_lines) > 1 and existing_lines[-1] == new_line:
            raise ValueError(f"Duplicate row refused: identical to the last line in logs/{filename}.")
        payload = ("\n".join([*existing_lines, new_line]) + "\n").encode("utf-8")
        commit_transaction(home, [(path, payload)])
    return new_line


def log_proof(home, area, proof, link, date=None):
    day = _validate_date(date)
    area_s = _one_line(area)
    proof_s = _validate_note(proof, label="proof")
    link_s = _one_line(link)
    if not area_s or not proof_s or not link_s:
        raise ValueError("proof requires non-empty --area, --proof, and --link.")
    _check_guard((area_s, proof_s, link_s))
    return _append_csv_row(home, "proofs.csv", [day, area_s, proof_s, link_s])


def log_ledger(home, task, model, minutes, note, date=None):
    day = _validate_date(date)
    task_s = _one_line(task)
    model_s = _one_line(model)
    note_s = _validate_note(note, label="note")
    if not task_s or not model_s or not note_s:
        raise ValueError("ledger requires non-empty --task, --model, and --note.")
    mins_s = _parse_float_range(minutes, "minutes", 0)
    _check_guard((task_s, model_s, note_s))
    return _append_csv_row(home, "ledger.csv", [day, task_s, model_s, mins_s, note_s])


def log_health(home, sleep, gym, energy, note="", date=None):
    day = _validate_date(date)
    sleep_s = _parse_float_range(sleep, "sleep", 0, 14)
    gym_s = _one_line(gym).lower()
    if gym_s not in ("yes", "no"):
        raise ValueError("Invalid gym value: expected 'yes' or 'no'.")
    if isinstance(energy, bool):
        raise ValueError("Invalid energy: expected an integer 1 to 5.")
    try:
        energy_i = int(str(energy).strip())
    except (TypeError, ValueError):
        raise ValueError(f"Invalid energy '{energy}': expected an integer 1 to 5.") from None
    if str(energy_i) != str(energy).strip() or not (1 <= energy_i <= 5):
        raise ValueError(f"Invalid energy '{energy}': must be an integer from 1 to 5.")
    note_s = _validate_note(note, label="note")
    _check_guard((note_s,))
    return _append_csv_row(home, "health.csv", [day, sleep_s, gym_s, str(energy_i), note_s])


def log_hours(home, area, hours, note="", date=None):
    day = _validate_date(date)
    area_s = _one_line(area).lower()
    if area_s not in VALID_HOURS_AREAS:
        raise ValueError(f"Invalid area '{area}': choose one of {', '.join(VALID_HOURS_AREAS)}.")
    hours_s = _parse_float_range(hours, "hours", 0, 24)
    note_s = _validate_note(note, label="note")
    _check_guard((note_s,))
    return _append_csv_row(home, "hours.csv", [day, area_s, hours_s, note_s])
