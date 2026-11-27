"""`lifeos next`: the one thing to do now, with the exact command. Read only, no model call.

The order is fixed and explained on the line it prints: damage in your files first, then an overdue task, an answer that
still has no rating, a deadline within seven days, a waiting item that is late or due within three days, the next open task,
and last a prompt to start something. It is `lifeos today` cut down to one decision."""
import datetime as dt

from . import deadlines, selfcheck, today
from .context import task_file

SOON_DAYS = 3
DEADLINE_DAYS = 7


def _waiting_gap(entry, day):
    try:
        return (dt.date.fromisoformat(str(entry.get("when"))[:10]) - day).days
    except ValueError:
        return None


def _rateable(home, item):
    try:
        task_file(home, item["task"])
        return True
    except (ValueError, FileNotFoundError):
        return False


def choose(home, day=None):
    """Return {kind, text, command}: what to do now and the command that does it."""
    day = day or dt.date.today()
    problems = [p for p in selfcheck.run(home) if p["level"] == "error"]
    if problems:
        return {"kind": "files", "text": f"{len(problems)} problem(s) in your own files; fix them before you trust a report.",
                "command": "lifeos selfcheck"}
    view = today.build(home, day)
    open_now = [t for t in view["open_tasks"] if t["status"] != "blocked"]
    first = open_now[0] if open_now else None
    if first and first["due"] and first["due"] < day.isoformat():
        return {"kind": "overdue", "text": f"{first['id']} is overdue (due {first['due']}): {first['goal']}",
                "command": f"lifeos route {first['id']}"}
    unrated = [item for item in view["unrated"] if _rateable(home, item)]
    if unrated:
        item = unrated[0]
        return {"kind": "rate", "text": f"{item['seat']} answered {item['task']} on {item['date']} and it has no rating yet.",
                "command": f"lifeos rate {item['task']} {item['seat']} <1-5> --note \"what was right or wrong\""}
    near = [d for d in view["deadlines"] if not d["approx"] and d["days"] <= DEADLINE_DAYS]
    if near:
        return {"kind": "deadline", "text": f"{near[0]['text']} ({near[0]['date']}, {deadlines.words(near[0]['days'])})",
                "command": "lifeos today"}
    due = sorted(((_waiting_gap(w, day), w) for w in view["waiting"]), key=lambda pair: (pair[0] is None, pair[0] or 0))
    if due and due[0][0] is not None and due[0][0] <= SOON_DAYS:
        gap, entry = due[0]
        when = "late" if gap < 0 else "due today" if gap == 0 else f"due in {gap} day(s)"
        return {"kind": "waiting", "text": f"{entry['item']} ({entry.get('who', '?')}, {when})", "command": "lifeos waiting list"}
    if open_now:
        task = open_now[0]
        return {"kind": "task", "text": f"{task['id']}: {task['goal']}", "command": f"lifeos route {task['id']}"}
    return {"kind": "none", "text": "Nothing is urgent.", "command": "lifeos task new \"<one sentence>\""}


def render(choice):
    return f"Next ({choice['kind']}): {choice['text']}\n  Run: {choice['command']}"
