"""Router that learns from outcomes: your 1-5 ratings per kind of work, and a recommendation only when the evidence is clear.

Ratings live in logs/ratings.csv (date, task, model, score, kind, note). The kind is the router's own reason line for the
task text (seats.kind), so a rating always counts toward the kind of work it was about. A model is recommended for a kind
only with at least MIN_N ratings for it and a mean that beats the router's default for that kind by at least MIN_GAP.
Otherwise the default stands (rule 2: numbers decide, but only enough numbers).
"""
import csv
import datetime as dt
from pathlib import Path

from . import guard, seats
from .store import append_csv_row, atomic_write_bytes, read_csv_rows

HEADER = ["date", "task", "model", "score", "kind", "note"]
MIN_N = 3
MIN_GAP = 1.0


class LearnError(Exception):
    pass


def _path(home):
    return Path(home) / "logs" / "ratings.csv"


def read_ratings(home):
    rows = []
    for r in read_csv_rows(_path(home), ("score",)):
        try:
            rows.append({**r, "score": int(r["score"])})
        except (TypeError, ValueError):
            continue
    return rows


def add_rating(home, task_id, model, score, text, today=None, note=""):
    all_models = set(seats.CHAINS)
    if model not in all_models:
        raise LearnError(f"Unknown model '{model}'. Choose from: {', '.join(sorted(all_models))}.")
    try:
        score = int(score)
    except (TypeError, ValueError):
        raise LearnError("The score is a whole number from 1 to 5.") from None
    if not 1 <= score <= 5:
        raise LearnError("The score is a whole number from 1 to 5.")
    note = " ".join(str(note or "").split())[:200]
    if guard.scan_text(note):
        raise LearnError("The note looks like private data (rule 9). Rewrite it without the number or key.")
    path = _path(home)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(path, (",".join(HEADER) + "\n").encode("utf-8"))
    row = {"date": (today or dt.date.today()).isoformat(), "task": task_id, "model": model, "score": score,
           "kind": seats.kind(text)[3], "note": note}
    append_csv_row(path, [row[k] for k in HEADER])
    return row


def report(home):
    """{kind: {model: {n, mean}}}"""
    grouped = {}
    for r in read_ratings(home):
        grouped.setdefault(r["kind"], {}).setdefault(r["model"], []).append(r["score"])
    return {k: {m: {"n": len(v), "mean": round(sum(v) / len(v), 2)} for m, v in models.items()}
            for k, models in grouped.items()}


def recommend(home, text):
    """Return {model|None, kind, default, gap, why}. A model is named only when the evidence is clear."""
    default, _reviewer, _level, kind = seats.kind(text)
    stats = report(home).get(kind, {})
    ready = {m: s for m, s in stats.items() if s["n"] >= MIN_N}
    out = {"model": None, "kind": kind, "default": default, "gap": 0.0}
    if not ready:
        out["why"] = f"fewer than {MIN_N} ratings for any model on this kind of work, so the default ({default}) stands"
        return out
    best = max(ready, key=lambda m: ready[m]["mean"])
    base = ready[default]["mean"] if default in ready else min(s["mean"] for s in ready.values())
    gap = round(ready[best]["mean"] - base, 2)
    out["gap"] = gap
    if best == default or gap < MIN_GAP:
        out["why"] = f"no model beats {default} by {MIN_GAP:g} points with {MIN_N}+ ratings, so the default stands"
        return out
    out.update(model=best, why=f"{best} averages {ready[best]['mean']} over {ready[best]['n']} ratings, {gap} above the baseline")
    return out


def render(rep):
    if not rep:
        return "No ratings yet. Rate a finished task: lifeos rate <task> <model> <1-5>"
    lines = []
    for kind, models in sorted(rep.items()):
        lines.append(kind)
        for m, s in sorted(models.items(), key=lambda kv: -kv[1]["mean"]):
            lines.append(f"  {m:8} mean {s['mean']:.2f} over {s['n']}")
    return "\n".join(lines)
