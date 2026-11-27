"""The data files for a dashboard, from the home folder, in one command. No model call, nothing leaves the laptop.

`lifeos dash-export --out DIR` writes five JSON lists a dashboard can load: numbers (counts only), runs by seat, ratings with
their notes, tasks (id, status, due, goal) and an optional waiting list kept by hand in `waiting.json` in the home folder.
The files hold task goals and rating notes: they are private. Publish them only to a page only you can open.
"""
import json
from pathlib import Path

from . import learn, numbers, tasks, today

TITLE_MAX = 90


def _numbers_rows(home, commands):
    data = numbers.build(home, commands=commands)
    guard, ledger, savings = data["guard"], data["ledger"], data["savings"]
    return [
        {"metric": "Python modules", "value": data["modules"], "unit": "stdlib only"},
        {"metric": "Lines of code", "value": data["code_lines"], "unit": ""},
        {"metric": "Test functions", "value": data["tests"], "unit": ""},
        {"metric": "Commands", "value": data["commands"] or 0, "unit": ""},
        {"metric": "Fake identifiers blocked", "value": guard["blocked"], "unit": f"of {guard['total']}"},
        {"metric": "Harmless texts flagged", "value": guard["benign_flagged"], "unit": f"of {guard['benign_total']}"},
        {"metric": "Ledger records", "value": ledger["records"], "unit": "chain intact" if ledger["ok"] else "CHAIN BROKEN"},
        {"metric": "Tokens per cloud run", "value": savings.get("avg_sent", 0), "unit": "avg, measured"},
    ], data["runs_by_model"]


def _ratings_rows(home):
    return [{"date": r.get("date", ""), "task": r.get("task", ""), "model": r.get("model", ""), "score": r["score"],
             "note": r.get("note", "")} for r in learn.read_ratings(home)]


def _task_rows(home):
    return [{"id": t["id"], "status": t["status"], "due": t["due"], "title": (t["goal"] or "")[:TITLE_MAX]}
            for t in tasks.list_tasks(home)]


def export(home, out_dir, commands=None):
    """Write the five files; return their paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    num_rows, by_model = _numbers_rows(home, commands)
    runs = sorted(({"model": m, "runs": n} for m, n in by_model.items()), key=lambda r: (-r["runs"], r["model"]))
    files = {"numbers.json": num_rows, "runs.json": runs, "ratings.json": _ratings_rows(home),
             "tasks.json": _task_rows(home), "waiting.json": today.read_waiting(home)}
    written = []
    for name, rows in files.items():
        path = out / name
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        written.append(path)
    return written
