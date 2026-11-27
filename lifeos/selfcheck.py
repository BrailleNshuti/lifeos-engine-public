"""`lifeos selfcheck`: is your own data sound? One pass over the files the engine trusts: the run ledger chain, the task
files (`lint`), the ratings log and the waiting list. It reads and prints; it never repairs anything. Damage exits 1, a
softer finding is a warning. (`lifeos selftest` checks the engine itself; this checks your files.)"""
import csv
import datetime as dt
import io
import json
from pathlib import Path

from . import lint, verify

RATING_HEAD = ["date", "task", "model", "score"]


def _problem(area, where, message, level="error"):
    return {"area": area, "where": where, "message": message, "level": level}


def check_ledger(home):
    result = verify.verify_chain(home)
    return [_problem("ledger", "logs/runs.jsonl", e) for e in result["errors"]]


def check_tasks(home):
    return [_problem("tasks", f"tasks/{p['task']}.md", p["problem"]) for p in lint.check(home)]


def check_ratings(home):
    path = Path(home) / "logs" / "ratings.csv"
    if not path.exists():
        return []
    where = "logs/ratings.csv"
    text = path.read_bytes().decode("utf-8", errors="replace").lstrip("﻿")
    try:
        rows = list(csv.reader(io.StringIO(text, newline="")))
    except csv.Error as err:
        return [_problem("ratings", where, f"the file cannot be read as CSV: {err}")]
    if not rows or [c.strip().lower() for c in rows[0][:4]] != RATING_HEAD:
        return [_problem("ratings", where, "the header should start with date,task,model,score")]
    out = []
    ids = {p.stem for p in (Path(home) / "tasks").glob("T-*.md")}
    for number, row in enumerate(rows[1:], 2):
        if not row:
            continue
        if len(row) < 4:
            out.append(_problem("ratings", f"{where}:{number}", "the row has fewer than four columns"))
            continue
        day, task, _model, score = (c.strip() for c in row[:4])
        try:
            dt.date.fromisoformat(day)
        except ValueError:
            out.append(_problem("ratings", f"{where}:{number}", f"'{day}' is not a date (YYYY-MM-DD)"))
        if score not in {"1", "2", "3", "4", "5"}:
            out.append(_problem("ratings", f"{where}:{number}", f"the score '{score}' is not a whole number from 1 to 5"))
        if ids and not any(i == task or i.startswith(task) for i in ids):
            out.append(_problem("ratings", f"{where}:{number}", f"no task file matches '{task}'", "warning"))
    return out


def check_waiting(home):
    path = Path(home) / "waiting.json"
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as err:
        return [_problem("waiting", "waiting.json", f"the file is not valid JSON: {err}")]
    if not isinstance(rows, list):
        return [_problem("waiting", "waiting.json", "the file should hold a list of {item, who, when}")]
    out = []
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict) or not str(row.get("item") or "").strip():
            out.append(_problem("waiting", f"waiting.json item {number}", "an entry needs a non-empty 'item'"))
    return out


def run(home):
    problems = []
    for step in (check_ledger, check_tasks, check_ratings, check_waiting):
        problems += step(home)
    return problems


FIXES = {
    "ledger": "lifeos verify shows the line; restore a good copy with lifeos backup --restore <backup folder>, or keep the file and note the break",
    "tasks": "open the task file and fix the line named; lifeos lint checks it again",
    "ratings": "open logs/ratings.csv at the line named and fix it, or remove a wrong row with lifeos unrate <task>",
    "waiting": "fix waiting.json by hand, or rewrite the list with lifeos waiting add",
}


def render(problems):
    if not problems:
        return "selfcheck: your files are sound (ledger chain, tasks, ratings, waiting list)."
    errors = sum(1 for p in problems if p["level"] == "error")
    lines = [f"selfcheck: {errors} problem(s), {len(problems) - errors} warning(s). Nothing was changed."]
    for p in problems:
        lines.append(f"  {p['level']:7} {p['area']:8} {p['where']}: {p['message']}")
    for area in sorted({p["area"] for p in problems if p["level"] == "error"}):
        lines.append(f"  fix {area}: {FIXES[area]}")
    return "\n".join(lines)


def exit_code(problems):
    return 1 if any(p["level"] == "error" for p in problems) else 0
