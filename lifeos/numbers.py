"""'Engine in numbers': one page of facts that can be checked, built from the code, the guard score and the ledger.

Only counts leave the home (how many runs, how many words), never a task id, a path or any text. Run `lifeos numbers`
and publish the page if you want; the same command reproduces it.
"""
import collections
import datetime as dt
from pathlib import Path

from . import calibrate, canary, learn, verify, vocab
from .store import read_run_records


def _package_stats():
    pkg = Path(__file__).parent
    files = sorted(p for p in pkg.glob("*.py"))
    lines = sum(len(p.read_text(encoding="utf-8").splitlines()) for p in files)
    tests = pkg.parent / "tests"
    count = sum(p.read_text(encoding="utf-8").count("\ndef test_") for p in tests.glob("test_*.py")) if tests.is_dir() else None
    return len(files), lines, count


def build(home, commands=None):
    modules, lines, tests = _package_stats()
    records = read_run_records(home)
    chain = verify.verify_chain(home)
    score = canary.guard_score()
    by_model = collections.Counter(str(r.get("model") or "?").split(":", 1)[0] for r in records)
    return {
        "modules": modules, "code_lines": lines, "tests": tests, "commands": commands,
        "guard": {"blocked": score["blocked"], "total": score["total"],
                  "benign_flagged": len(score["benign_flagged"]), "benign_total": score["benign_total"]},
        "ledger": {"records": chain["records"], "chained": chain["chained"], "legacy": chain["legacy"], "ok": chain["ok"]},
        "runs_by_model": dict(sorted(by_model.items())),
        "practice": {"ratings": len(learn.read_ratings(home)),
                     "predictions": calibrate.report(home)["resolved"] + calibrate.report(home)["open"],
                     "vocab_words": len(vocab.stats(home)["words"])},
    }


def render(d, today=None):
    day = (today or dt.date.today()).isoformat()
    g, led, pr = d["guard"], d["ledger"], d["practice"]
    rows = [
        ("Python modules (standard library only)", d["modules"]),
        ("Lines of code", d["code_lines"]),
        ("Test functions", d["tests"] if d["tests"] is not None else "n/a here"),
        ("Commands", d["commands"] if d["commands"] is not None else "n/a here"),
        ("Privacy guard on generated fake identifiers", f"{g['blocked']} of {g['total']} blocked"),
        ("Harmless texts wrongly flagged", f"{g['benign_flagged']} of {g['benign_total']}"),
        ("Run ledger", f"{led['records']} records, {led['chained']} hash-chained, {led['legacy']} older; "
                       + ("chain intact" if led["ok"] else "CHAIN BROKEN")),
        ("Ratings, predictions, own words", f"{pr['ratings']}, {pr['predictions']}, {pr['vocab_words']}"),
    ]
    lines = [f"# Engine in numbers · {day}", "", "Every figure is reproduced by `lifeos numbers`. Counts only; no task text.", "",
             "| What | Value |", "|---|---|"] + [f"| {a} | {b} |" for a, b in rows]
    if d["runs_by_model"]:
        lines += ["", "Runs by model: " + ", ".join(f"{m} {n}" for m, n in d["runs_by_model"].items())]
    return "\n".join(lines) + "\n"
