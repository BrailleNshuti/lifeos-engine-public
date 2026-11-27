"""`lifeos earn`: rule 10 as a table. For each part of the system, did it earn its place in the last N days?

It counts entries in the logs each part writes (runs, ratings, predictions, vocabulary, experiments, decisions, ledger,
proofs, tasks). No part is removed or paused for you: the verdict is a question for the Sunday review, backed by a number.
A part with no log of its own (a read-only command) cannot be judged here and is not listed.
"""
import datetime as dt
import statistics
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


def latency(home, today=None, days=30):
    """Per seat, from the run ledger: calls that answered (count, median and worst seconds) and calls that failed.
    A failed call is counted but never timed; a record without a usable duration is left out. No model call."""
    today = today or dt.date.today()
    since = today - dt.timedelta(days=days)
    seats = {}
    for r in read_run_records(Path(home)):
        seat = str(r.get("model") or "").split(":", 1)[0].strip()
        try:
            day = dt.date.fromisoformat(str(r.get("date") or str(r.get("started_at") or "")[:10])[:10])
        except ValueError:
            continue
        if not seat or not since < day <= today:
            continue
        row = seats.setdefault(seat, {"ok": [], "failed": 0})
        status = r.get("status")
        if status == "ok":
            ms = r.get("duration_ms")
            if isinstance(ms, (int, float)) and not isinstance(ms, bool) and ms > 0:
                row["ok"].append(ms / 1000)
        elif status not in ("blocked", None):
            row["failed"] += 1
    return [{"seat": s, "ok": len(v["ok"]), "failed": v["failed"],
             "median_s": round(statistics.median(v["ok"]), 1) if v["ok"] else None,
             "worst_s": round(max(v["ok"]), 1) if v["ok"] else None}
            for s, v in sorted(seats.items()) if v["ok"] or v["failed"]]


FAILURE_WORDS = (
    ("timeout", ("did not answer within", "timed out", "timeout")),
    ("quota", ("quota", "usage limit", "rate limit", "hit your", "429", "too many requests")),
    ("signin", ("sign in", "signed in", "log in", "login", "unauthorized", "401", "api key", "credential", "authenticat")),
    ("max_turns", ("max turns",)),
    ("format", ("not valid json", "could not parse", "unexpected output", "empty answer")),
)


def failure_kind(rec):
    """Why a call did not answer, in one word: timeout, quota, signin, max_turns, format, tool_missing or other. Read from the
    status and the stored (already redacted) error line; nothing new is recorded."""
    status = str(rec.get("status") or "")
    if status == "timeout":
        return "timeout"
    if status == "tool_missing":
        return "tool_missing"
    text = str(rec.get("error") or "").lower()
    for kind, words in FAILURE_WORDS:
        if any(w in text for w in words):
            return kind
    return "other"


def failure_kinds(home, today=None, days=30):
    """{seat: {kind: count}} for calls that failed in the last `days` days (blocked calls are not failures)."""
    today = today or dt.date.today()
    since = today - dt.timedelta(days=days)
    out = {}
    for r in read_run_records(Path(home)):
        seat = str(r.get("model") or "").split(":", 1)[0].strip()
        status = r.get("status")
        if not seat or status in ("ok", "blocked", None):
            continue
        try:
            day = dt.date.fromisoformat(str(r.get("date") or str(r.get("started_at") or "")[:10])[:10])
        except ValueError:
            continue
        if since < day <= today:
            kinds = out.setdefault(seat, {})
            kind = failure_kind(r)
            kinds[kind] = kinds.get(kind, 0) + 1
    return out


def limit_days(home, today=None, days=30):
    """{seat: [YYYY-MM-DD, ...]} the days a seat's call failed on a usage limit or quota, oldest first, one entry per day."""
    today = today or dt.date.today()
    since = today - dt.timedelta(days=days)
    out = {}
    for r in read_run_records(Path(home)):
        seat = str(r.get("model") or "").split(":", 1)[0].strip()
        if not seat or r.get("status") in ("ok", "blocked", None) or failure_kind(r) != "quota":
            continue
        try:
            day = dt.date.fromisoformat(str(r.get("date") or str(r.get("started_at") or "")[:10])[:10])
        except ValueError:
            continue
        if since < day <= today and day.isoformat() not in out.setdefault(seat, []):
            out[seat].append(day.isoformat())
    return {seat: sorted(d) for seat, d in out.items() if d}


def render_latency(rows, days=30, why=None, limits=None):
    if not rows:
        return f"No timed calls in the last {days} days."
    lines = [f"Seat speed (last {days} days; seconds of calls that answered)", ""]
    for r in rows:
        median = f"{r['median_s']:>6.1f}" if r["median_s"] is not None else "     -"
        worst = f"{r['worst_s']:>6.1f}" if r["worst_s"] is not None else "     -"
        lines.append(f"{r['seat']:<8} {r['ok']:>3} ok {r['failed']:>3} failed  median {median} s  worst {worst} s")
        kinds = (why or {}).get(r["seat"])
        if kinds:
            lines.append("         why: " + ", ".join(f"{n} {k}" for k, n in sorted(kinds.items(), key=lambda kv: (-kv[1], kv[0]))))
        hit = (limits or {}).get(r["seat"])
        if hit:
            lines.append("         usage limit hit on: " + ", ".join(hit))
    return "\n".join(lines)
