"""Sunday review in numbers: for every part of the system, did it earn its place this week? (rule 10)

A part is used when it wrote at least one record in the last 7 days. No use for 14 days means the verdict is
"pause or remove". Counts and dates only; no task text.
"""
import csv
import datetime as dt
import json
from pathlib import Path

from . import study
from .store import read_run_records


def _dates_csv(path, col="date"):
    p = Path(path)
    if not p.exists():
        return []
    with p.open(encoding="utf-8", newline="") as fh:
        return [r[col] for r in csv.DictReader(fh) if r.get(col)]


def _day(value):
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _dates(home):
    home = Path(home)
    runs = read_run_records(home)
    return {
        "model runs": [r.get("date") or r.get("timestamp") for r in runs if not str(r.get("model", "")).startswith("review")],
        "reviews": [r.get("date") or r.get("timestamp") for r in runs if str(r.get("model", "")).startswith("review")],
        "ratings": _dates_csv(home / "logs" / "ratings.csv"),
        "predictions": _dates_csv(home / "logs" / "predictions.csv"),
        "vocabulary": _dates_csv(home / "logs" / "vocab.csv"),
        "study attempts": [a.get("date") for a in study.attempts(home)],
        "hours log": _dates_csv(home / "logs" / "hours.csv"),
        "proofs": _dates_csv(home / "logs" / "proofs.csv"),
    }


def build(home, today=None):
    today = today or dt.date.today()
    parts = []
    for name, raw in _dates(home).items():
        days = sorted(d for d in (_day(x) for x in raw) if d)
        week = sum(1 for d in days if 0 <= (today - d).days < 7)
        last = days[-1] if days else None
        idle = (today - last).days if last else None
        if week:
            verdict = "earned its place"
        elif idle is None or idle >= 14:
            verdict = "no use in 14+ days: pause or remove (rule 10)"
        else:
            verdict = "quiet this week"
        parts.append({"part": name, "week": week, "last": last.isoformat() if last else None, "verdict": verdict})
    return {"date": today.isoformat(), "parts": parts}


def render(d):
    lines = [f"Sunday review · {d['date']} · did every part earn its place?", "",
             "| Part | This week | Last use | Verdict |", "|---|---|---|---|"]
    lines += [f"| {p['part']} | {p['week']} | {p['last'] or 'never'} | {p['verdict']} |" for p in d["parts"]]
    return "\n".join(lines)
