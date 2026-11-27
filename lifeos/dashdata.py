"""The data files for a dashboard, from the home folder, in one command. No model call, nothing leaves the laptop.

`lifeos dash-export --out DIR` writes seven JSON lists a dashboard can load: numbers (counts only), runs by seat, ratings with
their notes, tasks (id, status, due, goal), an optional waiting list kept by hand in `waiting.json` in the home folder, what
left the laptop per cloud seat (counts only) and seat speed. All or none: the files are built in memory and staged in a
side folder first, so a failure while writing never leaves a mix of new and old files.
The files hold task goals and rating notes: they are private. Publish them only to a page only you can open.
"""
import json
import os
import shutil
import uuid
from pathlib import Path

from . import earn, egress, learn, numbers, tasks, today

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


def _egress_rows(home):
    return [{"seat": r["seat"], "sent": r["calls"], "failed": r["failed"], "tokens": r["tokens"], "last": r["last"]}
            for r in egress.report(home)]


def export(home, out_dir, commands=None):
    """Write the seven files, all or none; return their paths."""
    out = Path(out_dir)
    num_rows, by_model = _numbers_rows(home, commands)
    runs = sorted(({"model": m, "runs": n} for m, n in by_model.items()), key=lambda r: (-r["runs"], r["model"]))
    files = {"numbers.json": num_rows, "runs.json": runs, "ratings.json": _ratings_rows(home),
             "tasks.json": _task_rows(home), "waiting.json": today.read_waiting(home),
             "egress.json": _egress_rows(home), "latency.json": earn.latency(home)}
    payloads = {name: json.dumps(rows, ensure_ascii=False, indent=1).encode("utf-8") for name, rows in files.items()}
    out.mkdir(parents=True, exist_ok=True)
    stage = out / f".staging-{os.getpid()}-{uuid.uuid4().hex[:6]}"
    stage.mkdir()
    try:
        for name, data in payloads.items():
            (stage / name).write_bytes(data)
        old = {}
        for name in payloads:
            target = out / name
            if target.exists():
                old[name] = stage / f".old-{name}"
                shutil.copy2(target, old[name])
        installed = []
        try:
            for name in payloads:
                os.replace(stage / name, out / name)
                installed.append(name)
        except OSError:
            for name in reversed(installed):
                target = out / name
                if name in old:
                    os.replace(old[name], target)
                else:
                    target.unlink(missing_ok=True)
            raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return [out / name for name in payloads]
