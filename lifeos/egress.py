"""`lifeos egress`: what left this laptop. From the run ledger, per cloud seat: calls sent, tokens, failures, the last call.
Counts only; no prompt, answer or error text is ever read into the report. A call stopped by the guard before sending is
counted as blocked, not as sent. Local models never appear: they do not leave the laptop."""
import datetime as dt
from pathlib import Path

from . import seats
from .store import read_run_records


def report(home, today=None, days=30):
    today = today or dt.date.today()
    since = today - dt.timedelta(days=days)
    out = {}
    for r in read_run_records(Path(home)):
        seat = str(r.get("model") or "").split(":", 1)[0].strip()
        if seat not in seats.REMOTE:
            continue
        try:
            day = dt.date.fromisoformat(str(r.get("date") or str(r.get("started_at") or "")[:10])[:10])
        except ValueError:
            continue
        if not since < day <= today:
            continue
        row = out.setdefault(seat, {"seat": seat, "calls": 0, "tokens": 0, "failed": 0, "blocked": 0, "last": ""})
        status = r.get("status")
        if status == "blocked":
            row["blocked"] += 1
            continue
        row["calls"] += 1
        if status != "ok":
            row["failed"] += 1
        tokens = r.get("tokens")
        if isinstance(tokens, int) and not isinstance(tokens, bool) and tokens > 0:
            row["tokens"] += tokens
        row["last"] = max(row["last"], day.isoformat())
    return sorted(out.values(), key=lambda row: row["seat"])


def render(rows, days):
    if not rows:
        return f"Nothing left this laptop in the last {days} days."
    lines = [f"What left this laptop (last {days} days; counts only, never text)", ""]
    for r in rows:
        lines.append(f"{r['seat']:<8} {r['calls']:>4} sent {r['failed']:>3} failed {r['blocked']:>3} blocked  "
                     f"{r['tokens']:>9,} tokens  last {r['last']}")
    return chr(10).join(lines)
