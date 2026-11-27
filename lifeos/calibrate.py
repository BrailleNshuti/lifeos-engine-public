"""Decision calibration: say how sure you are before you know, then score yourself.

`predict` records a claim and a probability (1-99 %). `resolve` records what happened. The log (logs/predictions.csv)
only grows: a prediction row and a resolution row are separate lines. `report` gives the Brier score (0 is perfect,
0.25 is what always saying 50 % scores) and, per confidence band, what you said against what happened. Rules 2 and 6:
numbers decide, and a feeling of being sure is not evidence until the record shows it holds.
"""
import csv
import datetime as dt
from pathlib import Path

from . import guard
from .store import append_csv_row_creating, read_csv_rows

HEADER = ["date", "id", "kind", "value", "text"]
MIN_RESOLVED = 5
BANDS = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 100)]


class CalibrationError(Exception):
    pass


def _path(home):
    return Path(home) / "logs" / "predictions.csv"


def _rows(home):
    return read_csv_rows(_path(home), ("id", "kind", "value"))


def _append(home, values):
    path = _path(home)
    append_csv_row_creating(path, HEADER, values)


def predict(home, claim, percent, today=None):
    claim = " ".join(str(claim or "").split())
    if not claim:
        raise CalibrationError("Say what you expect to happen.")
    if guard.scan_text(claim):
        raise CalibrationError("The claim looks like private data (rule 9). Rewrite it without the number or key.")
    try:
        percent = int(percent)
    except (TypeError, ValueError):
        raise CalibrationError("The probability is a whole number from 1 to 99.") from None
    if not 1 <= percent <= 99:
        raise CalibrationError("The probability is a whole number from 1 to 99 (nothing is 0 or 100 percent).")
    ids = [r["id"] for r in _rows(home) if r["kind"] == "predict"]
    pid = f"P-{len(ids) + 1:03d}"
    _append(home, [(today or dt.date.today()).isoformat(), pid, "predict", percent, claim[:200]])
    return pid


def resolve(home, pid, happened, today=None):
    rows = _rows(home)
    if not any(r["id"] == pid and r["kind"] == "predict" for r in rows):
        raise CalibrationError(f"No prediction {pid}.")
    if any(r["id"] == pid and r["kind"] == "resolve" for r in rows):
        raise CalibrationError(f"{pid} is already resolved; the log only grows.")
    _append(home, [(today or dt.date.today()).isoformat(), pid, "resolve", 1 if happened else 0, ""])


def report(home):
    rows = _rows(home)
    said = {r["id"]: int(r["value"]) for r in rows if r["kind"] == "predict"}
    done = {r["id"]: int(r["value"]) for r in rows if r["kind"] == "resolve" and r["id"] in said}
    out = {"resolved": len(done), "open": len(said) - len(done), "brier": None, "bins": [], "verdict": ""}
    if not done:
        out["verdict"] = "Nothing resolved yet: too few results to judge."
        return out
    out["brier"] = sum((said[i] / 100 - o) ** 2 for i, o in done.items()) / len(done)
    for lo, hi in BANDS:
        ids = [i for i in done if (lo < said[i] <= hi)]
        if ids:
            out["bins"].append({"label": f"{lo}-{hi}", "n": len(ids),
                                "said": round(sum(said[i] for i in ids) / len(ids)),
                                "happened": round(100 * sum(done[i] for i in ids) / len(ids))})
    if len(done) < MIN_RESOLVED:
        out["verdict"] = f"Only {len(done)} resolved: too few results to judge (need {MIN_RESOLVED}+)."
        return out
    gap = sum(b["n"] * (b["said"] - b["happened"]) * (1 if b["said"] >= 50 else -1) for b in out["bins"]) / len(done)
    out["verdict"] = ("overconfident: your sure calls come true less often than you say" if gap > 8 else
                      "underconfident: your sure calls come true more often than you say" if gap < -8 else
                      "well calibrated so far")
    return out


def render(rep):
    if rep["brier"] is None:
        return rep["verdict"]
    lines = [f"Brier score {rep['brier']:.3f} (0 perfect, 0.250 = always saying 50 %) · {rep['resolved']} resolved, {rep['open']} open"]
    lines += [f"  {b['label']:>6} %  said {b['said']:>3} %, happened {b['happened']:>3} %  (n={b['n']})" for b in rep["bins"]]
    return "\n".join(lines + [rep["verdict"]])
