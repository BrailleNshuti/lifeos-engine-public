"""`lifeos today`: one screen for the day, built only from files you already keep.

The next task (overdue first, then the nearest due date), the open tasks, decisions whose revisit date has come, words
due for review, predictions still open and the running experiment. It reads and prints; it changes nothing and calls no
model. Rule 4: the hardest thing goes first, so the next task is named before anything else.
"""
import datetime as dt

from . import calibrate, decision, experiment, tasks, vocab

OPEN = ("todo", "doing", "blocked", "")


def _due_key(task):
    return (task["due"] or "9999-99-99", task["id"])


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
    return "\n".join(lines)
