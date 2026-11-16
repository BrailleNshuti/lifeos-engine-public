"""lifeos delegate: one task, the seat that fits it, and a replacement when that seat fails.

The choice comes from seats.py: what each model is good at, which seats are
resting, and which seats still have cloud budget. A missing tool or a failed
call is replaced by the next open seat. The task file records why under
## Route. That note is not sent to the next model.

Private and sensitive work never leaves this laptop. A failed local seat is
not replaced by a cloud seat.
"""
import datetime as dt
import re

from . import ask, seats
from .ask import ADAPTERS, run_ask  # noqa: F401  (ADAPTERS is patched in tests)
from .check import check_answer
from .context import task_file, visible_task
from .store import append_task_note, read_run_records

pick = seats.pick  # tests and older callers: (model, reason) from the task text


def task_text(path):
    """Goal, context and task only: not the route line, route notes, or earlier results."""
    raw = visible_task(path.read_text(encoding="utf-8"))
    goal = re.search(r"^goal:\s*(.+)$", raw, re.M)
    body = raw.split("## Result", 1)[0].split("---", 2)[-1]
    return f"{goal.group(1) if goal else ''}\n{body}"


def last_result(path):
    raw = visible_task(path.read_text(encoding="utf-8"))
    parts = re.split(r"^## Result · .*$", raw, flags=re.M)
    return parts[-1].strip() if len(parts) > 1 else ""


def _route_body(failed, winner):
    lines = []
    for item in failed:
        ref = f" ({item['run_id']})" if item.get("run_id") else ""
        lines.append(f"- {item['model']} {item['kind']}{ref}: {seats.brief(item.get('error') or item['kind'])}")
    if winner:
        lines.append(f"- {winner} answered.")
    body = "\n".join(lines)
    try:
        ask.check_text(body, "the route note", "The note keeps the seat and the kind only.")
    except ask.Blocked:
        safe = []
        for item in failed:
            ref = f" ({item['run_id']})" if item.get("run_id") else ""
            safe.append(f"- {item['model']} {item['kind']}{ref}")
        if winner:
            safe.append(f"- {winner} answered.")
        body = "\n".join(safe)
    return body


def _mark_route(home, path, failed, winner, today):
    if not failed:
        return
    heading = f"## Route · {today:%Y-%m-%d}"
    append_task_note(home, path, heading, _route_body(failed, winner))


def run_delegate(home, task_id, model=None, budget=6000, full=False, adapters=None, today=None, dry_run=False):
    """Run the task on the best open seat. Returns model, reason, tried, failures, path and the answer."""
    adapters = adapters if adapters is not None else ADAPTERS
    path = task_file(home, task_id)
    if model and model not in adapters:
        raise ValueError(f"Unknown model '{model}'. Choose one of: {', '.join(sorted(adapters))}.")
    tier = ask.task_data_tier(path)
    if tier == "SECRET":
        raise ask.Blocked("SECRET data cannot be sent to any model.")
    now = dt.datetime.now(dt.timezone.utc)
    resting = seats.pressure(read_run_records(home), now)
    chosen, reason, chain = seats.choose(task_text(path), tier, resting, explicit=model)
    chain = [name for name in chain if name in adapters]
    if not chain:
        raise ask.ToolMissing("no open seat has a model on this computer.")
    if dry_run:
        return {"model": chain[0], "reason": reason, "tried": [], "failed": [], "chain": chain,
                "path": path, "text": "", "flags": []}
    day = today or dt.date.today()
    tried = []
    failed = []
    for name in chain:
        tried.append(name)
        try:
            path = run_ask(home, name, task_id, budget, adapters=adapters, today=day, full=full)
        except ask.Blocked:
            raise
        except (ask.ToolMissing, ask.AskError) as error:
            kind = seats.failure_kind(str(error))
            failed.append({
                "model": name, "kind": kind, "error": str(error), "run_id": getattr(error, "run_id", None),
            })
            if name == chain[-1]:
                _mark_route(home, path, failed, None, day)
                raise
            if isinstance(error, ask.ToolMissing):
                reason += f" · {name} is not available ({error}); fell back"
            else:
                reason += f" · {name} failed ({kind}: {seats.brief(error)}); fell back"
            continue
        _mark_route(home, path, failed, name, day)
        return {
            "model": name, "reason": reason, "tried": tried, "failed": failed, "chain": chain,
            "path": path, "text": last_result(path), "flags": check_answer(last_result(path)),
        }
    raise ask.AskError("no seat answered.")
