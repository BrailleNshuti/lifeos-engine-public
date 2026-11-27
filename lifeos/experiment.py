"""Rule 11 as a tool: one tested rule change at a time, kept only if the numbers improve.

`start` records the change, the metric and the baseline (the days before today). `end`, after the trial days have run,
measures the same metric and decides: keep (clearly better), revert (not better) or inconclusive (too little data:
extend). An unproven change never stays by default. The log (logs/experiments.csv) only grows.
"""
import csv
import datetime as dt
import json
from pathlib import Path

from . import guard, learn
from .store import append_csv_row_creating, read_csv_rows, read_run_records

HEADER = ["date", "id", "kind", "metric", "value", "text"]
MIN_POINTS = 3
MIN_GAIN = 0.05  # 5 % better, or it is not an improvement


class ExperimentError(Exception):
    pass


def _day(value):
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _csv_rows(path):
    return read_csv_rows(path)


def _window(rows, lo, hi):
    return [r for r in rows if (d := _day(r.get("date"))) and lo <= d < hi]


def _runs(home):
    return [{"date": r.get("date") or str(r.get("started_at") or "")[:10], **r}
            for r in read_run_records(home) if r.get("command") == "ask"]


def _per_week(total, days):
    return total / (days / 7)


def _m_minutes(home, lo, hi):
    rows = _window(_csv_rows(Path(home) / "logs" / "ledger.csv"), lo, hi)
    return _per_week(sum(float(r["minutes_saved"] or 0) for r in rows), (hi - lo).days), len(rows)


def _m_proofs(home, lo, hi):
    rows = _window(_csv_rows(Path(home) / "logs" / "proofs.csv"), lo, hi)
    return _per_week(len(rows), (hi - lo).days), len(rows)


def _m_failed(home, lo, hi):
    rows = _window(_runs(home), lo, hi)
    return (sum(1 for r in rows if r.get("status") != "ok") / len(rows) if rows else 0.0), len(rows)


def _m_tokens(home, lo, hi):
    rows = [r for r in _window(_runs(home), lo, hi) if r.get("status") == "ok" and isinstance(r.get("tokens"), int)]
    return (sum(r["tokens"] for r in rows) / len(rows) if rows else 0.0), len(rows)


def _m_rating(home, lo, hi):
    rows = _window(learn.read_ratings(home), lo, hi)
    return (sum(int(r["score"]) for r in rows) / len(rows) if rows else 0.0), len(rows)


METRICS = {  # name: (function, higher_is_better, what it is)
    "minutes_saved": (_m_minutes, True, "minutes saved per week (logs/ledger.csv)"),
    "proofs": (_m_proofs, True, "proofs per week (logs/proofs.csv)"),
    "failed_rate": (_m_failed, False, "share of ask runs that did not finish ok"),
    "avg_tokens": (_m_tokens, False, "average tokens of ok ask runs"),
    "rating": (_m_rating, True, "mean of your 1-5 ratings"),
}


def _path(home):
    return Path(home) / "logs" / "experiments.csv"


def _rows(home):
    return read_csv_rows(_path(home), ("id", "kind", "value", "text"))


def _append(home, values):
    path = _path(home)
    append_csv_row_creating(path, HEADER, values)


def _state(home):
    exps = {}
    for r in _rows(home):
        e = exps.setdefault(r["id"], {"id": r["id"]})
        if r["kind"] == "start":
            e.update(start=r["date"], metric=r["metric"], baseline=float(r["value"]), **json.loads(r["text"]))
        else:
            e.update(verdict=json.loads(r["text"])["verdict"], after=float(r["value"]), ended=r["date"])
    return list(exps.values())


def start(home, change, metric, days=28, today=None):
    today = today or dt.date.today()
    change = " ".join(str(change or "").split())[:200]
    if not change:
        raise ExperimentError("Describe the one change you are testing.")
    if guard.scan_text(change):
        raise ExperimentError("The description looks like private data (rule 9).")
    if metric not in METRICS:
        raise ExperimentError(f"Unknown metric '{metric}'. Choose from: {', '.join(METRICS)}.")
    if not 7 <= int(days) <= 90:
        raise ExperimentError("Trial length is 7 to 90 days.")
    running = [e for e in _state(home) if "verdict" not in e]
    if running:
        raise ExperimentError(f"{running[0]['id']} is already running: finish it first (one tested change at a time, rule 11).")
    fn = METRICS[metric][0]
    baseline, points = fn(home, today - dt.timedelta(days=int(days)), today)
    eid = f"E-{len(_state(home)) + 1:03d}"
    _append(home, [today.isoformat(), eid, "start", metric, round(baseline, 4),
                   json.dumps({"change": change, "days": int(days), "baseline_points": points})])
    return {"id": eid, "metric": metric, "baseline": round(baseline, 4), "baseline_points": points, "days": int(days)}


def end(home, eid, today=None):
    today = today or dt.date.today()
    exp = next((e for e in _state(home) if e["id"] == eid), None)
    if exp is None:
        raise ExperimentError(f"No experiment {eid}.")
    if "verdict" in exp:
        raise ExperimentError(f"{eid} already ended: {exp['verdict']}.")
    first = _day(exp["start"])
    if (today - first).days < exp["days"]:
        raise ExperimentError(f"{eid} is not finished: {exp['days'] - (today - first).days} more day(s) of trial.")
    fn, higher, _what = METRICS[exp["metric"]]
    after, points = fn(home, first, today + dt.timedelta(days=1))
    base = exp["baseline"]
    if points < MIN_POINTS:
        verdict, why = "inconclusive", f"only {points} data point(s) in the trial (need {MIN_POINTS}): extend it and measure again"
    else:
        gain = ((after - base) / base if higher else (base - after) / base) if base else (1.0 if (after > 0) == higher and after != base else 0.0)
        if gain >= MIN_GAIN:
            verdict, why = "keep", f"{exp['metric']} went from {base:.2f} to {after:.2f}"
        else:
            verdict, why = "revert", f"{exp['metric']} went from {base:.2f} to {after:.2f}: not better, so the change does not stay (rule 11)"
    _append(home, [today.isoformat(), eid, "end", exp["metric"], round(after, 4), json.dumps({"verdict": verdict, "points": points})])
    return {"id": eid, "verdict": verdict, "baseline": base, "after": round(after, 4), "points": points, "why": why}


def list_all(home):
    return _state(home)


def render(rows):
    if not rows:
        return "No experiments yet. Start one: lifeos experiment start \"<change>\" --metric minutes_saved"
    out = []
    for e in rows:
        state = e.get("verdict", "running")
        out.append(f"{e['id']}  {e['start']}  {e['metric']}  {e['days']} days  {state}  {e['change']}")
    return "\n".join(out)
