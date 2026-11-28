"""`lifeos selfcheck`: is your own data sound? One read-only pass over the files the engine trusts. Damage exits 1; a
softer finding is a warning. (`lifeos selftest` checks the engine itself; this checks your files.)"""
import csv
import datetime as dt
import io
import json
from pathlib import Path

from . import lint, tasks, verify

from .store import read_bytes_retry

RATING_HEAD = ["date", "task", "model", "score"]
CSV_LOGS = [
    ("predictions", "predictions.csv", ["date", "id", "kind", "value", "text"],
     ("id", "kind", "value"), {"predict", "resolve"}),
    ("experiments", "experiments.csv", ["date", "id", "kind", "metric", "value", "text"],
     ("id", "kind", "metric", "value", "text"), {"start", "end"}),
    ("vocabulary", "vocab.csv", ["date", "word", "kind", "value", "text"],
     ("word", "kind", "value"), {"add", "review"}),
]

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
        rows = json.loads(read_bytes_retry(path).decode("utf-8-sig"))
    except (OSError, ValueError) as err:
        return [_problem("waiting", "waiting.json", f"the file is not valid JSON: {err}")]
    if not isinstance(rows, list):
        return [_problem("waiting", "waiting.json", "the file should hold a list of {item, who, when}")]
    out = []
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict) or not str(row.get("item") or "").strip():
            out.append(_problem("waiting", f"waiting.json item {number}", "an entry needs a non-empty 'item'"))
    return out


def check_csv_logs(home):
    out = []
    for area, name, header, required, kinds in CSV_LOGS:
        path, where = Path(home) / "logs" / name, f"logs/{name}"
        if not path.exists():
            continue
        try:
            rows = list(csv.reader(io.StringIO(read_bytes_retry(path).decode("utf-8-sig"), newline="")))
        except (OSError, UnicodeDecodeError, csv.Error) as err:
            out.append(_problem(area, where, f"the file cannot be read as UTF-8 CSV: {err}"))
            continue
        if not rows or rows[0] != header:
            out.append(_problem(area, where, f"the header should be {','.join(header)}"))
            continue
        positions = {name: header.index(name) for name in required}
        for number, row in enumerate(rows[1:], 2):
            if not row:
                continue
            if len(row) != len(header):
                out.append(_problem(area, f"{where}:{number}", f"the row should have {len(header)} columns"))
                continue
            try:
                dt.date.fromisoformat(row[0].strip())
            except ValueError:
                out.append(_problem(area, f"{where}:{number}", f"'{row[0].strip()}' is not a date (YYYY-MM-DD)"))
            missing = [name for name, index in positions.items() if not row[index].strip()]
            if missing:
                out.append(_problem(area, f"{where}:{number}", f"the row needs {', '.join(missing)}"))
            kind = row[header.index("kind")].strip()
            if kind and kind not in kinds:
                out.append(_problem(area, f"{where}:{number}", f"unknown kind '{kind}'"))
    return out


def check_decisions(home):
    out = []
    for path in sorted((Path(home) / "decisions").glob("D-*.md")):
        where = f"decisions/{path.name}"
        try:
            fields = tasks.read_frontmatter(path)
        except (OSError, UnicodeDecodeError) as err:
            out.append(_problem("decisions", where, f"the file cannot be read as UTF-8 text: {err}"))
            continue
        missing = [name for name in ("id", "title", "date", "revisit", "prediction") if not fields.get(name)]
        if missing:
            out.append(_problem("decisions", where, f"the front matter needs {', '.join(missing)}"))
            continue
        if fields["id"] != path.stem:
            out.append(_problem("decisions", where, f"id '{fields['id']}' does not match the file name"))
        for name in ("date", "revisit"):
            if fields[name] == "-":
                continue
            try:
                dt.date.fromisoformat(fields[name])
            except ValueError:
                out.append(_problem("decisions", where, f"'{fields[name]}' is not a {name} date (YYYY-MM-DD)"))
    return out

def run(home):
    problems = []
    for step in (check_ledger, check_tasks, check_ratings, check_waiting, check_csv_logs, check_decisions):
        problems += step(home)
    return problems


FIXES = {
    "ledger": "lifeos verify shows the line; restore a good copy with lifeos backup --restore <backup folder>, or keep the file and note the break",
    "tasks": "open the task file and fix the line named; lifeos lint checks it again",
    "ratings": "open logs/ratings.csv at the line named and fix it, or remove a wrong row with lifeos unrate <task>",
    "waiting": "fix waiting.json by hand, or rewrite the list with lifeos waiting add",
    "predictions": "fix logs/predictions.csv at the line named; lifeos schema shows its columns",
    "experiments": "fix logs/experiments.csv at the line named; lifeos schema shows its columns",
    "vocabulary": "fix logs/vocab.csv at the line named; lifeos schema shows its columns",
    "decisions": "open the decision file and fix the front matter named",}


def render(problems):
    if not problems:
        return "selfcheck: your files are sound (ledger, tasks, ratings, waiting, predictions, experiments, vocabulary, decisions)."
    errors = sum(1 for p in problems if p["level"] == "error")
    lines = [f"selfcheck: {errors} problem(s), {len(problems) - errors} warning(s). Nothing was changed."]
    for p in problems:
        lines.append(f"  {p['level']:7} {p['area']:8} {p['where']}: {p['message']}")
    for area in sorted({p["area"] for p in problems if p["level"] == "error"}):
        lines.append(f"  fix {area}: {FIXES[area]}")
    return "\n".join(lines)


def exit_code(problems):
    return 1 if any(p["level"] == "error" for p in problems) else 0
