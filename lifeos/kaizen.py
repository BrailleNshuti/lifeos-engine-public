"""Monthly System Health and Kaizen self-improving loop (Master Plan v2.3 Section 10.3).

Reads the last 28 days of logs/runs.jsonl, logs/ledger.csv, logs/proofs.csv, logs/hours.csv, logs/health.csv,
and system/changes.md to answer the five System Health questions with measured numbers and draft reviews/YYYY-MM.md.
"""
import csv
import datetime as dt
import re
from pathlib import Path

from .store import ASK_NOTE_PREFIX, atomic_write_bytes, model_call_flags, read_run_records, store_lock

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
TRACKED_AREAS = ("lab", "study", "german", "work")


def _parse_month_window(month=None, today=None):
    today = today or dt.date.today()
    if month:
        cleaned = str(month).strip()
        if not MONTH_RE.fullmatch(cleaned):
            raise ValueError(f"'{month}' is not a valid month. Use YYYY-MM (for example 2026-11).")
        year, mon = map(int, cleaned.split("-"))
        if mon == 12:
            end = dt.date(year + 1, 1, 1) - dt.timedelta(days=1)
        else:
            end = dt.date(year, mon + 1, 1) - dt.timedelta(days=1)
        label = cleaned
    else:
        end = today
        label = f"{today.year:04d}-{today.month:02d}"
    start = end - dt.timedelta(days=27)
    return label, start, end


def _csv_rows_in_window(path, start, end):
    path = Path(path)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for row in rows:
        try:
            day = dt.date.fromisoformat((row.get("date") or "").strip())
        except ValueError:
            continue
        if start <= day <= end:
            out.append(row)
    return out


def _runs_in_window(home, start, end):
    records = read_run_records(home, normalize=True)
    out = []
    for rec in records:
        try:
            day = dt.date.fromisoformat(str(rec.get("date") or "")[:10])
        except ValueError:
            continue
        if start <= day <= end:
            out.append(rec)
    return out


def _routing_waste(runs_rows, ledger_rows):
    non_ok = {}
    tokens_by_model = {}
    calls_by_model = {}
    for rec in runs_rows:
        st = rec.get("status") or "unknown"
        mdl = rec.get("model") or "review_group"
        calls_by_model[mdl] = calls_by_model.get(mdl, 0) + 1
        if st != "ok":
            non_ok[st] = non_ok.get(st, 0) + 1
        tok = rec.get("context_tokens")
        if isinstance(tok, int) and not isinstance(tok, bool):
            tokens_by_model[mdl] = tokens_by_model.get(mdl, 0) + tok

    flagged_by_model = {}
    for row in ledger_rows:
        note = (row.get("note") or "").strip()
        if not note.startswith(ASK_NOTE_PREFIX):
            continue
        mdl = (row.get("model") or "?").strip()
        if model_call_flags(note) > 0:
            flagged_by_model[mdl] = flagged_by_model.get(mdl, 0) + 1

    return {
        "total_runs": len(runs_rows),
        "non_ok_statuses": dict(sorted(non_ok.items())),
        "calls_by_model": dict(sorted(calls_by_model.items(), key=lambda kv: (-kv[1], kv[0]))),
        "tokens_by_model": dict(sorted(tokens_by_model.items(), key=lambda kv: (-kv[1], kv[0]))),
        "flagged_by_model": dict(sorted(flagged_by_model.items(), key=lambda kv: (-kv[1], kv[0]))),
    }


def _tier0_candidates(ledger_rows):
    counts = {}
    for row in ledger_rows:
        task_id = (row.get("task") or "").strip()
        if not task_id:
            continue
        counts[task_id] = counts.get(task_id, 0) + 1
    repeated = [(t, c) for t, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])) if c >= 2]
    return [{"task": t, "count": c} for t, c in repeated[:3]]


def _weakest_area(proof_rows, hours_rows, health_rows):
    proofs_by_area = {a: 0 for a in TRACKED_AREAS}
    for row in proof_rows:
        area = (row.get("area") or "").strip().lower()
        proofs_by_area[area] = proofs_by_area.get(area, 0) + 1

    hours_by_area = {a: 0.0 for a in TRACKED_AREAS}
    for row in hours_rows:
        area = (row.get("area") or "").strip().lower()
        try:
            hours_by_area[area] = round(hours_by_area.get(area, 0.0) + float(row.get("hours") or 0), 1)
        except ValueError:
            pass

    ranked = sorted(TRACKED_AREAS, key=lambda a: (proofs_by_area.get(a, 0), hours_by_area.get(a, 0.0), a))
    weakest = ranked[0]
    experiments = {
        "german": "Schedule five 30-minute attempt-first A1 blocks this week and log each with `lifeos log hours --area german`.",
        "study": "Complete one closed-book 10-question unit self-test in `learning/units/` before opening any AI chat.",
        "lab": "Ship one small tested PR on `lifeos-engine` or `iwa` and log the proof link.",
        "work": "Run one Prompt Lab card (`lifeos lab check/pack/score`) on synthetic data before copying to Console.",
    }
    return {
        "area": weakest,
        "proofs": proofs_by_area.get(weakest, 0),
        "hours": hours_by_area.get(weakest, 0.0),
        "health_days_logged": len(health_rows),
        "experiment": experiments.get(weakest, "Log one concrete proof in this area this week."),
    }


def _pending_trials(home, end_date):
    changes_path = Path(home) / "system" / "changes.md"
    if not changes_path.exists():
        return []
    pending = []
    for line in changes_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or "---" in line or "KEEP or REVERT" in line:
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 7:
            continue
        date_str, change, _reason, metric, _base, _res, verdict = cols[:7]
        if verdict not in ("-", ""):
            continue
        try:
            started = dt.date.fromisoformat(date_str)
            age_days = (end_date - started).days
        except ValueError:
            age_days = 0
        pending.append({
            "date": date_str,
            "change": change,
            "metric": metric,
            "age_days": age_days,
            "due_for_verdict": age_days >= 28,
        })
    return pending


def system_health(home, month=None, today=None):
    """Compute the 5-question Monthly System Health report (Section 10.3) over a 28-day window."""
    label, start, end = _parse_month_window(month=month, today=today)
    logs = Path(home) / "logs"
    ledger = _csv_rows_in_window(logs / "ledger.csv", start, end)
    proofs = _csv_rows_in_window(logs / "proofs.csv", start, end)
    hours = _csv_rows_in_window(logs / "hours.csv", start, end)
    health = _csv_rows_in_window(logs / "health.csv", start, end)
    runs = _runs_in_window(home, start, end)

    waste = _routing_waste(runs, ledger)
    tier0 = _tier0_candidates(ledger)
    weakest = _weakest_area(proofs, hours, health)
    trials = _pending_trials(home, end)

    if waste["non_ok_statuses"]:
        top_change = "Investigate non-ok model runs (`lifeos runs --status failed`) and tighten pre-flight checks."
    elif not hours or not health:
        top_change = "Use `lifeos log hours` and `lifeos log health` daily so `lifeos week` has complete lead measures."
    else:
        top_change = f"Raise the weekly proof floor in `{weakest['area']}` by +1 scored proof for the next 4 weeks."

    return {
        "month": label,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "routing_waste": waste,
        "tier0_candidates": tier0,
        "top_change": top_change,
        "weakest_area": weakest,
        "pending_trials": trials,
    }


def render_system_health(report):
    """Render the 5-question System Health report matching templates/system-health.md."""
    w = report["routing_waste"]
    non_ok = ", ".join(f"{k}:{v}" for k, v in w["non_ok_statuses"].items()) or "0 failed/blocked"
    models = ", ".join(f"{k} ({v} calls, {w['tokens_by_model'].get(k, 0)} tok)" for k, v in w["calls_by_model"].items()) or "no runs logged"
    flagged = ", ".join(f"{k}:{v}" for k, v in w["flagged_by_model"].items()) or "none"

    if report["tier0_candidates"]:
        t0_str = "; ".join(f"{c['task']} ({c['count']}x in ledger -> script/template)" for c in report["tier0_candidates"])
    else:
        t0_str = "no task repeated >=2x without a script"

    wk = report["weakest_area"]
    trials = report["pending_trials"]
    due = [t for t in trials if t["due_for_verdict"]]
    if due:
        trial_str = "; ".join(f"{t['date']} '{t['change']}' ({t['age_days']}d -> decide KEEP or REVERT)" for t in due)
    elif trials:
        trial_str = f"{len(trials)} active change(s) in system/changes.md (<28 days old; keep measuring)"
    else:
        trial_str = "no open trials in system/changes.md"

    slug = re.sub(r"[^a-z0-9]+", "-", wk["area"].lower()).strip("-") or "kaizen"
    lines = [
        f"# System Health · {report['month']} ({report['from']} to {report['to']})   (drafted by lifeos kaizen)",
        f"1. Routing waste (time or tokens): {w['total_runs']} runs ({models}); non-ok: {non_ok}; flagged answers: {flagged}",
        f"2. Move to Tier 0 for good: {t0_str}",
        f"3. The one change that helps most: {report['top_change']}",
        f"4. Weakest area and the smallest experiment: {wk['area']} ({wk['proofs']} proofs, {wk['hours']} h logged; "
        f"health logged {wk['health_days_logged']} d) -> {wk['experiment']}",
        f"5. Unused or heaviest part / 4-week trial check: {trial_str}",
        f"Proposed pull request: claude/kaizen-{report['month']}-{slug} | metric: {wk['area']} proofs/week | "
        f"baseline: {wk['proofs']} in 4w | review on: +28 days",
        "",
    ]
    return "\n".join(lines)


def draft_system_health(home, month=None, today=None):
    """Write reviews/<YYYY-MM>.md under the store lock without overwriting an existing file."""
    report = system_health(home, month=month, today=today)
    reviews_dir = Path(home) / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    target = reviews_dir / f"{report['month']}.md"
    with store_lock(home):
        if target.exists():
            raise ValueError(f"System Health review already exists: reviews/{target.name} (refusing to overwrite).")
        atomic_write_bytes(target, render_system_health(report).encode("utf-8"))
    return target
