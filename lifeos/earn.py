"""`lifeos earn`: rule 10 as a table. For each part of the system, did it earn its place in the last N days?

It counts entries in the logs each part writes (runs, ratings, predictions, vocabulary, experiments, decisions, ledger,
proofs, tasks). No part is removed or paused for you: the verdict is a question for the Sunday review, backed by a number.
A part with no log of its own (a read-only command) cannot be judged here and is not listed.
"""
import datetime as dt
from pathlib import Path

from .store import read_csv_rows, read_run_records

PARTS = [  # name, kind, source, filter
    ("ask / delegate / panel", "runs", None),
    ("debate", "debate", None),
    ("rate / learn", "csv", "ratings.csv"),
    ("predict / calibration", "csv", "predictions.csv"),
    ("vocab", "csv", "vocab.csv"),
    ("experiment", "csv", "experiments.csv"),
    ("decide", "dir", "decisions"),
    ("ledger", "csv", "ledger.csv"),
    ("prove / proofs", "csv", "proofs.csv"),
    ("tasks", "dir", "tasks"),
]


def _dates(home, kind, source):
    home = Path(home)
    if kind in ("runs", "debate"):
        # a debate use is a recorded answer (round 1 to 3); its start and its skipped or failed seats are not uses
        mine = (lambda r: r.get("command") == "debate" and r.get("status") == "ok" and (r.get("round") or 0) >= 1)
        wanted = mine if kind == "debate" else (lambda r: r.get("command") != "debate")
        raw = [r.get("date") or str(r.get("started_at") or "")[:10] for r in read_run_records(home) if wanted(r)]
    elif kind == "csv":
        raw = [r.get("date") for r in read_csv_rows(home / "logs" / source, ("date",))]
    else:
        raw = []
        for p in (home / source).glob("*.md"):
            if p.name[:1] in "DT" and len(p.name) > 8 and p.name[2:8].isdigit():
                raw.append(f"20{p.name[2:4]}-{p.name[4:6]}-{p.name[6:8]}")
    out = []
    for value in raw:
        try:
            out.append(dt.date.fromisoformat(str(value)[:10]))
        except ValueError:
            continue
    return sorted(out)


def review(home, today=None, days=30):
    today = today or dt.date.today()
    since = today - dt.timedelta(days=days)
    rows = []
    for name, kind, source in PARTS:
        dates = _dates(home, kind, source)
        uses = sum(1 for d in dates if since < d <= today)
        last = dates[-1].isoformat() if dates else "-"
        verdict = ("earns its place" if uses else "never used: pause or remove?" if not dates else "quiet: pause or remove?")
        rows.append({"part": name, "uses": uses, "last": last, "verdict": verdict, "days": days})
    return rows


def render(rows):
    days = rows[0]["days"] if rows else 30
    lines = [f"Did each part earn its place? (uses in the last {days} days)", ""]
    lines += [f"{r['part']:<24} {r['uses']:>4}  last {r['last']:<10}  {r['verdict']}" for r in rows]
    lines += ["", "A number to bring to the Sunday review. Nothing was paused or removed."]
    return "\n".join(lines)
