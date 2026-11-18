"""`lifeos decide`: short decision records with a revisit date and an optional calibrated prediction (rules 2, 6, 8).

decisions/D-YYMMDD-slug.md holds the choice, the reason, a revisit date and, if you give one, the id of a
`calibrate` prediction ("I expect X, 80 %"). `due` lists decisions whose revisit date has come, so they get judged
against the numbers instead of staying forever. Files are never overwritten.
"""
import datetime as dt
import re
from pathlib import Path

from . import calibrate, guard, tasks

TEMPLATE = """---
id: {id}
title: {title}
date: {date}
revisit: {revisit}
prediction: {prediction}
---
# {title}

Why: {why}
"""


class DecisionError(Exception):
    pass


def _clean(text):
    return " ".join(str(text or "").split())


def record(home, title, why, revisit="", predict="", percent=None, today=None):
    today = today or dt.date.today()
    title, why = _clean(title)[:120], _clean(why)[:400]
    if not title or not why:
        raise DecisionError("A decision needs a title and a reason.")
    if guard.scan_text(title + " " + why):
        raise DecisionError("The text looks like private data (rule 9).")
    if revisit:
        try:
            dt.date.fromisoformat(revisit)
        except ValueError:
            raise DecisionError("The revisit date is YYYY-MM-DD.") from None
    pid = ""
    if predict:
        try:
            pid = calibrate.predict(home, predict, percent if percent is not None else 70, today=today)
        except calibrate.CalibrationError as err:
            raise DecisionError(str(err)) from None
    folder = Path(home) / "decisions"
    folder.mkdir(exist_ok=True)
    base, n = f"D-{today:%y%m%d}-{tasks.slugify(title)}", 2
    path = folder / f"{base}.md"
    while path.exists():
        path, n = folder / f"{base}-{n}.md", n + 1
    path.write_text(TEMPLATE.format(id=path.stem, title=title, date=today.isoformat(), revisit=revisit or "-",
                                    prediction=pid or "-", why=why), encoding="utf-8")
    return path


def list_all(home):
    out = []
    for path in sorted((Path(home) / "decisions").glob("D-*.md")):
        meta = tasks.read_frontmatter(path)
        out.append({"id": path.stem, "title": meta.get("title", path.stem), "date": meta.get("date", ""),
                    "revisit": meta.get("revisit", "-"), "prediction": meta.get("prediction", "-")})
    return out


def due(home, today=None):
    today = (today or dt.date.today()).isoformat()
    return [d for d in list_all(home) if re.match(r"\d{4}-\d\d-\d\d$", d["revisit"]) and d["revisit"] <= today]


def render(rows):
    if not rows:
        return "No decisions."
    return "\n".join(f"{d['id']}  revisit {d['revisit']}  {d['prediction']}  {d['title']}" for d in rows)
