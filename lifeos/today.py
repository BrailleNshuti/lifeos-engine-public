"""`lifeos today`: one screen for the day, built only from files you already keep.

The next task (overdue first, then the nearest due date), the open tasks, decisions whose revisit date has come, words
due for review, predictions still open and the running experiment. It reads and prints; it changes nothing and calls no
model. Rule 4: the hardest thing goes first, so the next task is named before anything else.
"""
import datetime as dt
import json
from pathlib import Path

from . import backup, calibrate, decision, experiment, learn, tasks, vocab
from .store import read_bytes_retry, read_run_records

OPEN = ("todo", "doing", "blocked", "")
BACKUP_DAYS = 14


def _due_key(task):
    return (task["due"] or "9999-99-99", task["id"])


def read_waiting(home):
    """The hand-kept waiting list (`waiting.json` in the home folder): a list of {item, who, when}. Never raises."""
    try:
        rows = json.loads(read_bytes_retry(Path(home) / "waiting.json").decode("utf-8-sig"))
    except (OSError, ValueError):
        return []
    return [r for r in rows if isinstance(r, dict) and r.get("item")] if isinstance(rows, list) else []


def unrated(home, today=None, min_age_days=1):
    """Answers a seat gave at least `min_age_days` ago that have no rating yet: [{task, seat, date}], oldest first, one per
    task and seat. Rule 11 needs the numbers, and a rating given a week late is a guess. Reads only; never raises."""
    today = today or dt.date.today()
    rated = {(str(r.get("task") or ""), str(r.get("model") or "")) for r in learn.read_ratings(home)}
    seen, out = set(), []
    for r in read_run_records(Path(home)):
        seat = str(r.get("model") or "").split(":", 1)[0].strip()
        task = str(r.get("task_id") or "")
        if r.get("status") != "ok" or r.get("command") not in ("ask", "delegate") or not seat or seat == "review" or not task:
            continue
        try:
            day = dt.date.fromisoformat(str(r.get("date") or "")[:10])
        except ValueError:
            continue
        if (today - day).days < min_age_days or (task, seat) in seen:
            continue
        seen.add((task, seat))
        if any(m == seat and (task == t or task.startswith(t)) for t, m in rated):
            continue
        out.append({"task": task, "seat": seat, "date": day.isoformat()})
    return sorted(out, key=lambda row: (row["date"], row["task"]))


def days_left(when, today=None):
    """'in 3 days', 'today', '2 days late' for an ISO date; '' for any other text such as 'anytime'."""
    try:
        gap = (dt.date.fromisoformat(str(when)[:10]) - (today or dt.date.today())).days
    except ValueError:
        return ""
    if gap == 0:
        return "today"
    if gap == 1:
        return "tomorrow"
    return f"in {gap} days" if gap > 0 else f"{-gap} days late"


def build(home, today=None):
    today = today or dt.date.today()
    iso = today.isoformat()
    open_tasks = sorted((t for t in tasks.list_tasks(home) if t["status"] in OPEN), key=_due_key)
    running = [e for e in experiment.list_all(home) if "verdict" not in e]
    return {
        "date": iso,
        "next_task": open_tasks[0] if open_tasks else None,
        "open_tasks": open_tasks,
        "overdue": sum(1 for t in open_tasks if t["due"] and t["due"] < iso),
        "decisions_due": len(decision.due(home, today=today)),
        "words_due": len(vocab.due(home, today=today)),
        "predictions_open": calibrate.report(home)["open"],
        "experiment": running[0] if running else None,
        "waiting": read_waiting(home),
        "unrated": unrated(home, today),
        "backup_age": backup.age_days(home, today),
    }


def render(v):
    lines = [f"Today {v['date']}", ""]
    t = v["next_task"]
    if not t:
        lines.append("Nothing open. Add one: lifeos task new \"<one sentence>\"")
    else:
        late = " (OVERDUE)" if t["due"] and t["due"] < v["date"] else ""
        lines.append(f"Next: {t['id']}  due {t['due'] or '-'}{late}")
        lines.append(f"      {t['goal']}")
        lines += [f"  also open: {o['id']}  due {o['due'] or '-'}  {o['goal']}" for o in v["open_tasks"][1:6]]
    lines.append("")
    lines.append(f"Overdue {v['overdue']} | decisions to revisit {v['decisions_due']} | words due {v['words_due']} | "
                 f"predictions open {v['predictions_open']}")
    e = v["experiment"]
    if e:
        lines.append(f"Experiment {e['id']} running: {e['change']} ({e['metric']}, ends after {e['days']} days from {e['start']})")
    waiting = v.get("waiting") or []
    if waiting:
        lines += ["", f"Waiting ({len(waiting)})"]
        for w in waiting[:5]:
            left = days_left(w.get("when"), dt.date.fromisoformat(v["date"]))
            lines.append(f"  - {w['item']} ({w.get('who', '?')}, {w.get('when', '?')}{', ' + left if left else ''})")
        if len(waiting) > 5:
            lines.append(f"  ... and {len(waiting) - 5} more in waiting.json")
    age = v.get("backup_age")
    if age is None or age > BACKUP_DAYS:
        lines += ["", "Backup: " + ("never made" if age is None else f"{age} days old") + f" (more than {BACKUP_DAYS} days is overdue): lifeos backup --out <folder outside your home>"]
    pending = v.get("unrated") or []
    if pending:
        lines += ["", f"Not rated yet ({len(pending)}): rate while you still remember what was wrong"]
        lines += [f"  - {p['task']}  {p['seat']}  {p['date']}   lifeos rate {p['task']} {p['seat']} <1-5> --note \"...\"" for p in pending[:5]]
    return "\n".join(lines)
