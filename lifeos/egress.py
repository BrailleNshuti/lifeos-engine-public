"""`lifeos egress`: what left this laptop. From the run ledger, per cloud seat: calls sent, tokens, failures, the last call.
Counts only; no prompt, answer or error text is ever read into the report. A call stopped by the guard before sending is
counted as blocked, not as sent. Local models never appear: they do not leave the laptop."""
import datetime as dt
from pathlib import Path

from . import seats
from .store import read_run_records


def report(home, today=None, days=30, task=None):
    today = today or dt.date.today()
    since = today - dt.timedelta(days=days)
    out = {}
    for r in read_run_records(Path(home)):
        seat = str(r.get("model") or "").split(":", 1)[0].strip()
        if seat not in seats.REMOTE:
            continue
        if task and not str(r.get("task_id") or "").startswith(task):
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


def render(rows, days, task=None):
    where = f" for {task}" if task else ""
    if not rows:
        return f"Nothing left this laptop{where} in the last {days} days."
    lines = [f"What left this laptop{where} (last {days} days; counts only, never text)", ""]
    for r in rows:
        lines.append(f"{r['seat']:<8} {r['calls']:>4} sent {r['failed']:>3} failed {r['blocked']:>3} blocked  "
                     f"{r['tokens']:>9,} tokens  last {r['last']}")
    return chr(10).join(lines)


def over_share(home, today=None):
    """One warning per cloud seat whose tokens in the last 7 days are above its weekly share (`seats.SHARES`)."""
    out = []
    for row in report(home, today=today, days=7):
        share = seats.SHARES.get(row["seat"])
        if share and row["tokens"] > share:
            out.append(f"WARNING: {row['seat']} used {row['tokens']:,} tokens in the last 7 days; its weekly share is {share:,}.")
    return out


def share_line(home, seat, today=None):
    """One line after a cloud call: this seat's tokens in the last 7 days against its weekly share, or '' for a local seat or a
    seat with no share. Counts only."""
    share = seats.SHARES.get(seat)
    if not share:
        return ""
    rows = [r for r in report(home, today=today, days=7) if r["seat"] == seat]
    used = rows[0]["tokens"] if rows else 0
    return f"weekly share: {seat} {used:,} of {share:,} tokens in the last 7 days ({round(100 * used / share)} %)"
