"""`lifeos sunday`: the numbers for the weekly review on one page. Reads the logs and calls no model. It writes nothing
unless you pass `--save`, which keeps the page as `reports/week-YYYY-Www.md` so every week leaves a file."""
import datetime as dt
from pathlib import Path

from . import earn, guard, learn, mistakes, stale, today as todaymod
from .store import atomic_write_bytes


class SaveRefused(Exception):
    pass

WEEK_DAYS = 7


def _ratings_block(home, today):
    since = today - dt.timedelta(days=WEEK_DAYS)
    rows = []
    for r in learn.read_ratings(home):
        try:
            day = dt.date.fromisoformat(str(r.get("date", ""))[:10])
        except ValueError:
            continue
        if since < day <= today:
            rows.append(r)
    if not rows:
        return "No ratings this week."
    return "\n".join(f"{r['date']}  {r['model']:<8} {r['score']}/5  {r.get('task', '')}  {r.get('note', '')[:80]}" for r in rows)


def _waiting_block(home, today):
    rows = todaymod.read_waiting(home)
    if not rows:
        return "Nothing is waiting."
    lines = []
    for w in rows:
        left = todaymod.days_left(w.get("when"), today)
        lines.append(f"- {w['item']} ({w.get('who', '?')}, {w.get('when', '?')}{', ' + left if left else ''})")
    return "\n".join(lines)


def build(home, today=None):
    home = Path(home)
    today = today or dt.date.today()
    open_mistakes = mistakes.quiz(home, 5)
    mistake_lines = "\n".join(f"{n}. {m['prompt']}" for n, m in enumerate(open_mistakes, 1)) or "No open mistakes."
    speed = earn.render_latency(earn.latency(home, today=today), why=earn.failure_kinds(home, today=today))
    if not speed.startswith("Seat speed"):
        speed = "Seat speed" + chr(10) + speed
    parts = [
        f"Sunday review, {today.isoformat()}",
        "",
        earn.render(earn.review(home, today=today)),
        "",
        speed,
        "",
        "Ratings this week",
        _ratings_block(home, today),
        "",
        "Waiting",
        _waiting_block(home, today),
        "",
        "Stale",
        stale.render(stale.find(home, today=today)),
        "",
        "Open mistakes",
        mistake_lines,
        "",
        "Next: read these, then run the weekly-review skill to write the review itself.",
    ]
    return "\n".join(parts)


def week_file(home, today=None):
    today = today or dt.date.today()
    year, week, _ = today.isocalendar()
    return Path(home) / "reports" / f"week-{year}-W{week:02d}.md"


def save(home, today=None):
    """Write the page to reports/week-YYYY-Www.md (a second run in the same week replaces that week's file). Refuses, and
    writes nothing, when the page holds anything the guard would block."""
    today = today or dt.date.today()
    page = build(home, today)
    blocks = [f for f in guard.scan_text(page) if f[1] == "BLOCK"]
    if blocks:
        raise SaveRefused(f"The page holds {len(blocks)} sensitive finding(s), so it was not saved. Fix the note or task that carries it.")
    path = week_file(home, today)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(path, (page + chr(10)).encode("utf-8"))
    return path
