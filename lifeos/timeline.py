"""`lifeos timeline [--weeks N]`: proofs and minutes saved per ISO week, oldest first, with a bar for each.

Plain text from logs/proofs.csv and logs/ledger.csv; empty weeks are shown, because a gap is information (rule 1: proof or
it did not happen). Read-only.
"""
import datetime as dt
from pathlib import Path

from .store import read_csv_rows


def _week(day):
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def _days(path, column="date"):
    for row in read_csv_rows(path, (column,)):
        try:
            yield dt.date.fromisoformat(row[column][:10]), row
        except ValueError:
            continue


def weeks(home, today=None, count=8):
    today = today or dt.date.today()
    names = []
    for back in range(count - 1, -1, -1):
        name = _week(today - dt.timedelta(weeks=back))
        if name not in names:
            names.append(name)
    table = {n: {"week": n, "proofs": 0, "minutes": 0} for n in names}
    for day, _row in _days(Path(home) / "logs" / "proofs.csv"):
        if _week(day) in table:
            table[_week(day)]["proofs"] += 1
    for day, row in _days(Path(home) / "logs" / "ledger.csv"):
        try:
            minutes = int(float(row.get("minutes_saved") or 0))
        except ValueError:
            continue
        if _week(day) in table:
            table[_week(day)]["minutes"] += minutes
    return [table[n] for n in names]


def render(rows):
    top = max([r["proofs"] for r in rows] + [1])
    lines = [f"{'week':<9} {'proofs':>6}  {'':<20} minutes saved"]
    for r in rows:
        bar = "#" * round(20 * r["proofs"] / top)
        lines.append(f"{r['week']:<9} {r['proofs']:>6}  {bar:<20} {r['minutes']}")
    return "\n".join(lines)
