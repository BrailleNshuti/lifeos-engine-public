"""Deadlines from `now.md`: the owner's real outside dates, read from its `## Deadlines` section, with the days left.

A line looks like `- Fri 18 Dec: pay the invoice`, `- 1 to 12 Mar 2027: exams` or `- Jan 2027: lease ends`. The
year is taken when written; otherwise it is the one (this year, last or next) whose weekday matches the weekday in the line,
or the next occurrence of the day. A month and year alone counts as the first of that month and is marked approximate. A line
that cannot be read is left out, never guessed. Also reads the `updated YYYY-MM-DD` date in the title of `now.md`. Read only."""
import datetime as dt
import re
from pathlib import Path

MONTHS = {m: n for n, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_LINE = re.compile(r"^-\s+(?:(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*\s+)?(\d{1,2})(?:\s+to\s+(\d{1,2}))?\s+([A-Z][a-z]{2})[a-z]*(?:\s+(\d{4}))?\s*:\s*(.+)$")
MONTH_LINE = re.compile(r"^-\s+([A-Z][a-z]{2})[a-z]*\s+(\d{4})\s*:\s*(.+)$")
UPDATED = re.compile(r"updated\s+(\d{4}-\d{2}-\d{2})")


def _section(text, name):
    body, inside = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line[3:].strip().lower().startswith(name)
            continue
        if inside:
            body.append(line.strip())
    return body


def _day(weekday, day, month, year, today):
    if year:
        try:
            return dt.date(year, month, day)
        except ValueError:
            return None
    options = []
    for y in (today.year - 1, today.year, today.year + 1):
        try:
            options.append(dt.date(y, month, day))
        except ValueError:
            continue
    if weekday:
        options = [d for d in options if WEEKDAYS[d.weekday()] == weekday.lower()[:3]]
    options = [d for d in options if d >= today - dt.timedelta(days=60)]
    return min(options, key=lambda d: abs((d - today).days)) if options else None


def read(home, today=None):
    """[{date, text, approx, days}] sorted by date, from now.md. [] when there is no file or no section."""
    today = today or dt.date.today()
    try:
        text = (Path(home) / "now.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out = []
    for line in _section(text, "deadlines"):
        m = DAY_LINE.match(line)
        if m:
            weekday, day, _end, mon, year, what = m.groups()
            when = _day(weekday, int(day), MONTHS.get(mon.lower(), 0), int(year) if year else None, today) if mon.lower() in MONTHS else None
            approx = False
        else:
            m = MONTH_LINE.match(line)
            if not m or m.group(1).lower() not in MONTHS:
                continue
            when, approx, what = dt.date(int(m.group(2)), MONTHS[m.group(1).lower()], 1), True, m.group(3)
        if when:
            out.append({"date": when.isoformat(), "text": what.split(" · ")[0].strip(), "approx": approx, "days": (when - today).days})
    return sorted(out, key=lambda d: d["date"])


def upcoming(home, today=None, within=60):
    """The deadlines from today on that are at most `within` days away."""
    return [d for d in read(home, today) if 0 <= d["days"] <= within]


def now_age_days(home, today=None):
    """Days since the `updated YYYY-MM-DD` date in the first line of now.md, or None when there is none."""
    today = today or dt.date.today()
    try:
        first = (Path(home) / "now.md").read_text(encoding="utf-8", errors="replace").splitlines()[0]
        return (today - dt.date.fromisoformat(UPDATED.search(first).group(1))).days
    except (OSError, IndexError, AttributeError, ValueError):
        return None


def words(days):
    return "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
