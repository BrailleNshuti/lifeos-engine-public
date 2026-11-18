"""`lifeos stale`: what has been sitting too long: open tasks, unresolved predictions, decisions past their revisit date.

Age comes from the date in the file name (T-YYMMDD-...) or the log row. Read-only and never closes anything for you;
a thing that stays open must be finished, resolved or dropped on purpose.
"""
import datetime as dt
from pathlib import Path

from . import decision, tasks
from .store import read_csv_rows

OPEN = ("inbox", "todo", "doing", "blocked", "")


def _task_date(task_id):
    try:
        return dt.date(2000 + int(task_id[2:4]), int(task_id[4:6]), int(task_id[6:8]))
    except ValueError:
        return None


def find(home, today=None, days=14):
    today = today or dt.date.today()
    old_tasks = []
    for t in tasks.list_tasks(home):
        born = _task_date(t["id"])
        if t["status"] in OPEN and born and (today - born).days > days:
            old_tasks.append({"id": t["id"], "status": t["status"] or "-", "age": (today - born).days, "goal": t["goal"]})
    rows = read_csv_rows(Path(home) / "logs" / "predictions.csv",
                         ("id", "kind", "date"))
    resolved = {r["id"] for r in rows if r["kind"] == "resolve"}
    old_preds = []
    for r in rows:
        try:
            age = (today - dt.date.fromisoformat(r["date"][:10])).days
        except ValueError:
            continue
        if r["kind"] == "predict" and r["id"] not in resolved and age > days:
            old_preds.append({"id": r["id"], "age": age, "claim": r.get("text", "")})
    due = decision.due(home, today=today)
    return {"days": days, "tasks": old_tasks, "predictions": old_preds, "decisions": due,
            "total": len(old_tasks) + len(old_preds) + len(due)}


def render(out):
    if not out["total"]:
        return f"Nothing stale (older than {out['days']} days)."
    lines = []
    lines += [f"task        {t['id']}  {t['status']}, {t['age']} days old  {t['goal']}" for t in out["tasks"]]
    lines += [f"prediction  {p['id']}  open {p['age']} days  {p['claim']}  (lifeos resolve {p['id']} yes|no)" for p in out["predictions"]]
    lines += [f"decision    {d['id']}  revisit {d['revisit']}  {d['title']}" for d in out["decisions"]]
    return "\n".join(lines) + f"\n\n{out['total']} item(s) to finish, resolve or drop on purpose."
