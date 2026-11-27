"""`lifeos sunday`: the numbers for the weekly review on one page. Reads the logs, calls no model, writes nothing."""
import datetime as dt
from pathlib import Path

from . import earn, learn, mistakes, stale

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
        "Stale",
        stale.render(stale.find(home, today=today)),
        "",
        "Open mistakes",
        mistake_lines,
        "",
        "Next: read these, then run the weekly-review skill to write the review itself.",
    ]
    return "\n".join(parts)
