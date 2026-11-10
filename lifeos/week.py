"""Weekly numbers from the logs: the part of the Sunday review a machine can do honestly."""
import csv
import datetime as dt
from pathlib import Path


def week_bounds(week=None, today=None):
    """Monday and Sunday of an ISO week ('2026-W47') or of the week containing today."""
    if week:
        year, num = week.upper().split("-W")
        start = dt.date.fromisocalendar(int(year), int(num), 1)
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


def week_numbers(home, week=None, today=None):
    start, end = week_bounds(week, today)
    logs = Path(home) / "logs"
    ledger = [r for r in _rows(logs / "ledger.csv") if _in_range(r, start, end)]
    proofs = [r for r in _rows(logs / "proofs.csv") if _in_range(r, start, end)]
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
    iso = start.isocalendar()
    return {
        "week": f"{iso[0]}-W{iso[1]:02d}", "from": start.isoformat(), "to": end.isoformat(),
        "ledger_lines": len(ledger), "net_hours_saved": round(minutes / 60, 1),
        "proofs": len(proofs), "proofs_by_area": dict(sorted(by_area.items())),
        "proof_links": [((r.get("proof") or "").strip(), (r.get("link") or "").strip()) for r in proofs],
    }


def render_markdown(n):
    areas = ", ".join(f"{k} {v}" for k, v in n["proofs_by_area"].items())
    lines = [
        f"# Week {n['week']} ({n['from']} to {n['to']}): numbers from the logs",
        "",
        f"- Proofs: {n['proofs']}" + (f" ({areas})" if areas else ""),
        f"- Net time saved by AI: {n['net_hours_saved']} h from {n['ledger_lines']} ledger lines",
        "",
        "## Proof links",
    ]
    lines += [f"- {proof}: {link}" for proof, link in n["proof_links"]] or ["- none this week"]
    lines += ["", "Items 3 to 8 of the weekly review are yours; these numbers come only from the logs."]
    return "\n".join(lines)
