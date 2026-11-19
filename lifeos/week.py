"""Weekly numbers from the logs: the part of the Sunday review a machine can do honestly."""
import csv
import datetime as dt
import re
from pathlib import Path

from .store import ASK_NOTE_PREFIX, atomic_write_bytes, model_call_flags, read_csv_rows, store_lock

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
    return read_csv_rows(path)


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


def render_weekly_draft(n):
    """Render a Sunday weekly review draft matching templates/weekly-review.md with Item 1 & 2 pre-filled from logs."""
    areas = ", ".join(f"{k} {v}" for k, v in n["proofs_by_area"].items())
    proof_summary = f"{n['proofs']}" + (f" ({areas})" if areas else "")
    hours_part = ""
    if n.get("hours_by_area"):
        h_areas = ", ".join(f"{k} {v} h" for k, v in n["hours_by_area"].items())
        hours_part = f" | logged hours: {n['total_hours']} h ({h_areas})"
    health = n.get("health") or {}
    health_part = ""
    if health.get("days"):
        health_part = (
            f" | health ({health['days']} d): sleep {health['sleep_avg']} h, "
            f"gym {health['gym_days']} d, energy {health['energy_avg']}/5"
        )
    d = n["delegation"]
    del_part = (
        f"delegation: {d['calls']} calls ({', '.join(f'{m} {c}' for m, c in d['by_model'].items())}), "
        f"flagged {d['flagged']}/{d['calls']}"
        if d["calls"]
        else "delegation: 0 calls"
    )
    proof_lines = [f"   - {proof}: {link}" for proof, link in n["proof_links"]] or ["   - none logged yet"]
    lines = [
        f"# Weekly review · {n['week']} · {n['to']}   (30 to 40 minutes)",
        f"1. Numbers (drafted from logs): proofs {proof_summary} | net time saved {n['net_hours_saved']} h "
        f"({n['ledger_lines']} ledger lines){hours_part}{health_part} | {del_part} | system time __ h | AI spend EUR __",
        "2. Proofs (links), with one Engine change I used in real work this week:",
        *proof_lines,
        "3. What did I avoid?",
        "4. Where did I fool myself?",
        "5. What failed, and the one cause:",
        "6. Red team (ChatGPT / Codex, facts only): weakest point | hardest useful next step",
        "7. Top 3 next week (one per bet, each with done-when):",
        "8. One system fix:",
        "Brake check: system time over the cap two weeks in a row? Then pause one part (rules.md, law 10).",
        "",
    ]
    return "\n".join(lines)


def draft_weekly_review(home, week=None, today=None):
    """Write reviews/<week>.md pre-filled with log numbers under the store lock. Never overwrites an existing review."""
    n = week_numbers(home, week=week, today=today)
    reviews_dir = Path(home) / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    target = reviews_dir / f"{n['week']}.md"
    with store_lock(home):
        if target.exists():
            raise ValueError(f"Review draft already exists: reviews/{target.name} (refusing to overwrite).")
        atomic_write_bytes(target, render_weekly_draft(n).encode("utf-8"))
    return target


def _extract_now_facts(home):
    """Extract only factual Bets, Top 3, and Deadlines sections from now.md (no opinions or chat history)."""
    now_path = Path(home) / "now.md"
    if not now_path.exists():
        return ""
    text = now_path.read_text(encoding="utf-8")
    sections = []
    for header in ("## Bets", "## Top 3", "## Deadlines"):
        match = re.search(rf"(^{re.escape(header)}.*?)(?=^## |\Z)", text, flags=re.M | re.S)
        if match:
            sections.append(match.group(1).strip())
    return "\n\n".join(sections)


def build_redteam_pack(home, week=None, today=None):
    """Build a facts-only Red-Team prompt pack from weekly log numbers and now.md."""
    n = week_numbers(home, week=week, today=today)
    facts = _extract_now_facts(home)
    lines = [
        f"# Red-Team Pack · {n['week']} ({n['from']} to {n['to']}) · Facts Only",
        "",
        "Instruction for reviewer (Rule 7):",
        "Read only the measured weekly numbers and active commitments below.",
        "Do not flatter. Answer in two short sections:",
        "1. Weakest point in this week's execution or numbers.",
        "2. The single hardest useful next step for next week.",
        "",
        "## Measured Weekly Numbers (from logs/)",
        render_markdown(n),
    ]
    if facts:
        lines += ["", "## Current Commitments (from now.md)", facts]
    return "\n".join(lines) + "\n"

