"""Weekly numbers from the logs: the part of the Sunday review a machine can do honestly."""
import csv
import datetime as dt
from pathlib import Path

from .store import ASK_NOTE_PREFIX, model_call_flags

ASKED = ASK_NOTE_PREFIX  # compatibility name; the contract itself lives in store.py


def week_bounds(week=None, today=None):
    """Monday and Sunday of an ISO week ('2026-W47') or of the week containing today."""
    if week:
        try:
            year, num = week.upper().split("-W")
            start = dt.date.fromisocalendar(int(year), int(num), 1)
        except ValueError:
            raise ValueError(f"'{week}' is not a week. Use the form 2026-W47 (year, -W, week number 1 to 53).") from None
    else:
        today = today or dt.date.today()
        start = today - dt.timedelta(days=today.weekday())
    return start, start + dt.timedelta(days=6)


def _rows(path):
    path = Path(path)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _in_range(row, start, end):
    try:
        day = dt.date.fromisoformat((row.get("date") or "").strip())
    except ValueError:
        return False
    return start <= day <= end


def _delegation(ledger):
    """Model calls of the week: how many, per model (most used first) and how many answers the check flagged."""
    by_model, flagged = {}, 0
    for row in ledger:
        note = (row.get("note") or "").strip()
        if not note.startswith(ASKED):
            continue
        model = (row.get("model") or "?").strip()
        by_model[model] = by_model.get(model, 0) + 1
        flagged += model_call_flags(note) > 0
    by_model = dict(sorted(by_model.items(), key=lambda item: (-item[1], item[0])))
    return {"calls": sum(by_model.values()), "by_model": by_model, "flagged": flagged}


def _hours_summary(hours_rows):
    by_area = {}
    for row in hours_rows:
        area = (row.get("area") or "?").strip()
        try:
            h = float(row.get("hours") or 0)
        except ValueError:
            continue
        by_area[area] = round(by_area.get(area, 0.0) + h, 2)
    ordered = {k: (int(v) if v.is_integer() else round(v, 1)) for k, v in sorted(by_area.items())}
    total = round(sum(by_area.values()), 1)
    return ordered, total


def _health_summary(health_rows):
    sleeps, energies, gym_days = [], [], 0
    for row in health_rows:
        try:
            sleeps.append(float(row.get("sleep_h") or 0))
        except ValueError:
            pass
        if (row.get("gym") or "").strip().lower() == "yes":
            gym_days += 1
        try:
            energies.append(float(row.get("energy_1_5") or 0))
        except ValueError:
            pass
    return {
        "days": len(health_rows),
        "sleep_avg": round(sum(sleeps) / len(sleeps), 1) if sleeps else None,
        "gym_days": gym_days,
        "energy_avg": round(sum(energies) / len(energies), 1) if energies else None,
    }


def week_numbers(home, week=None, today=None):
    start, end = week_bounds(week, today)
    logs = Path(home) / "logs"
    ledger = [r for r in _rows(logs / "ledger.csv") if _in_range(r, start, end)]
    proofs = [r for r in _rows(logs / "proofs.csv") if _in_range(r, start, end)]
    hours_rows = [r for r in _rows(logs / "hours.csv") if _in_range(r, start, end)]
    health_rows = [r for r in _rows(logs / "health.csv") if _in_range(r, start, end)]
    minutes = 0
    for row in ledger:
        try:
            minutes += int(float(row.get("minutes_saved") or 0))
        except ValueError:
            pass
    by_area = {}
    for row in proofs:
        area = (row.get("area") or "?").strip()
        by_area[area] = by_area.get(area, 0) + 1
    hours_by_area, total_hours = _hours_summary(hours_rows)
    iso = start.isocalendar()
    return {
        "week": f"{iso[0]}-W{iso[1]:02d}", "from": start.isoformat(), "to": end.isoformat(),
        "ledger_lines": len(ledger), "net_hours_saved": round(minutes / 60, 1),
        "proofs": len(proofs), "proofs_by_area": dict(sorted(by_area.items())),
        "proof_links": [((r.get("proof") or "").strip(), (r.get("link") or "").strip()) for r in proofs],
        "delegation": _delegation(ledger),
        "hours_by_area": hours_by_area,
        "total_hours": total_hours,
        "health": _health_summary(health_rows),
    }


def _delegation_line(d):
    if not d["calls"]:
        return "Delegation: none this week"
    models = ", ".join(f"{model} {count}" for model, count in d["by_model"].items())
    return f"Delegation: {d['calls']} calls ({models}); flagged answers: {d['flagged']} of {d['calls']}"


def render_markdown(n):
    areas = ", ".join(f"{k} {v}" for k, v in n["proofs_by_area"].items())
    lines = [
        f"# Week {n['week']} ({n['from']} to {n['to']}): numbers from the logs",
        "",
        f"- Proofs: {n['proofs']}" + (f" ({areas})" if areas else ""),
        f"- Net time saved by AI: {n['net_hours_saved']} h from {n['ledger_lines']} ledger lines",
    ]
    if n.get("hours_by_area"):
        h_areas = ", ".join(f"{k} {v} h" for k, v in n["hours_by_area"].items())
        lines.append(f"- Logged hours: {n['total_hours']} h ({h_areas})")
    health = n.get("health") or {}
    if health.get("days"):
        lines.append(
            f"- Health ({health['days']} d): sleep avg {health['sleep_avg']} h, "
            f"gym {health['gym_days']} d, energy avg {health['energy_avg']}/5"
        )
    lines += [
        "",
        _delegation_line(n["delegation"]),
        "",
        "## Proof links",
    ]
    lines += [f"- {proof}: {link}" for proof, link in n["proof_links"]] or ["- none this week"]
    lines += ["", "Items 3 to 8 of the weekly review are yours; these numbers come only from the logs."]
    return "\n".join(lines)

