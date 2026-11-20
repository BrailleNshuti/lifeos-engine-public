"""`lifeos selftest`: run the commands on a throwaway copy of the demo home and say PASS or FAIL for each.

It never touches your real notes and calls no model. The runner is passed in (the CLI's own `main`), so every step
goes through the same entry point you use. Output of each step is captured; a failing step names itself.
"""
import contextlib
import io
import re
import shutil
import tempfile
from pathlib import Path

TASK = "T-261116"
STEPS = [
    ("demo", ["demo"]),
    ("canary", ["canary"]),
    ("proof", ["{h}", "prove", "--skip-tests"]),
    ("task list", ["{h}", "task", "list"]),
    ("week", ["{h}", "week"]),
    ("context", ["{h}", "context", TASK, "--explain"]),
    ("route", ["{h}", "route", TASK]),
    ("ask dry run", ["{h}", "ask", "claude", TASK, "--dry-run"]),
    ("delegate dry run", ["{h}", "delegate", TASK, "--dry-run"]),
    ("seats", ["{h}", "seats"]),
    ("guard on the demo home", ["{h}", "guard", "{files}"]),
    ("predict", ["{h}", "predict", "selftest works", "--p", "70"]),
    ("resolve", ["{h}", "resolve", "P-001", "yes"]),
    ("calibration", ["{h}", "calibration"]),
    ("vocab add", ["{h}", "vocab", "add", "die Wohnung", "the flat", "--example", "Meine Wohnung ist in Bonn."]),
    ("vocab quiz", ["{h}", "vocab", "quiz", "--reveal"]),
    ("vocab answer", ["{h}", "vocab", "answer", "die Wohnung", "good"]),
    ("rate", ["{h}", "rate", TASK, "claude", "4"]),
    ("learn", ["{h}", "learn"]),
    ("mistakes", ["{h}", "mistakes"]),
    ("digest", ["{h}", "digest"]),
    ("ledger verify", ["{h}", "verify"]),
    ("savings", ["{h}", "savings"]),
    ("numbers page", ["{h}", "numbers", "--html", "{out}/n.html"]),
    ("today", ["{h}", "today"]),
    ("earn", ["{h}", "earn"]),
    ("lint", ["{h}", "lint"]),
    ("stale", ["{h}", "stale"]),
    ("timeline", ["{h}", "timeline", "--weeks", "4"]),
    ("decide", ["{h}", "decide", "add", "selftest decision", "--why", "proves the command", "--revisit", "2099-01-01"]),
    ("decide list", ["{h}", "decide", "list"]),
    ("experiment", ["{h}", "experiment", "start", "selftest change", "--metric", "minutes_saved"]),
    ("export", ["{h}", "export", "--out", "{out}/evidence.md"]),
    ("redact", ["redact", "{out}/evidence.md", "--out", "{out}/redacted"]),
    ("backup", ["{h}", "backup", "--out", "{out}/bk"]),
    ("schema", ["schema"]),
    ("pipeline", ["{h}", "pipeline", "before-push", "--run"]),
]


def _example():
    return Path(__file__).resolve().parent.parent / "examples" / "demo-home"


DEBATE_NAMES = ["debate start", "debate record claude", "debate record codex", "debate next", "debate score", "debate run dry",
                "ledger verify after debate"]
DEBATE_STEPS = len(DEBATE_NAMES)
QUESTION = "Is a short bounded retry safe when a file is briefly held open by another program?"
ANSWER = "1. A short bounded retry is safe when only a brief sharing violation is retried.\n2. A lasting lock must still raise the original error."


def _exec(runner, argv):
    """Run one command through the runner. Returns (exit code, captured output); a crash is code 1 with its type."""
    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            code = runner(argv)
    except SystemExit as exit_:
        code = exit_.code if isinstance(exit_.code, int) else 1
    except Exception as err:  # a crash is a FAIL with its type, not a traceback wall
        code, sink = 1, io.StringIO(f"{type(err).__name__}: {err}")
    return code, sink.getvalue()


def _row(name, code, text):
    return {"name": name, "ok": code == 0, "code": code, "tail": text.strip().splitlines()[-1:] or [""]}


def _debate(runner, home, root):
    """A debate round trip with no model: start, two recorded answers, the next prompts, a score, a dry run, then the ledger
    chain. If it cannot start, every step is still reported as a failure so the count never shrinks in silence."""
    rows = []

    def step(name, argv):
        code, text = _exec(runner, ["--home", str(home)] + argv)
        rows.append(_row(name, code, text))
        return text

    started = step("debate start", ["debate", "start", QUESTION, "--seats", "claude,codex", "--seed", "selftest"])
    found = re.search(r"D-\d{6}-[0-9a-f]{6}", started)
    if not rows[0]["ok"] or not found:
        return rows + [_row(name, 1, "skipped: the debate did not start") for name in DEBATE_NAMES[1:]]
    did = found.group(0)
    for seat in ("claude", "codex"):
        answer = root / f"{seat}-answer.txt"
        answer.write_text(ANSWER, encoding="utf-8")
        step(f"debate record {seat}", ["debate", "record", did, "--round", "1", "--seat", seat, "--file", str(answer)])
    step("debate next", ["debate", "next", did])
    step("debate score", ["debate", "score", did])
    step("debate run dry", ["debate", "run", did])
    step("ledger verify after debate", ["verify"])
    return rows


def run(runner, example=None):
    example = Path(example or _example())
    root = Path(tempfile.mkdtemp(prefix="lifeos-selftest-"))
    home = root / "home"
    try:
        shutil.copytree(example, home)
        files = [str(p) for p in sorted(home.rglob("*.md"))]
        rows = []
        for name, template in STEPS:
            argv = []
            for part in template:
                if part == "{h}":
                    argv += ["--home", str(home)]
                elif part == "{files}":
                    argv += files
                else:
                    argv.append(part.replace("{out}", str(root)))
            rows.append(_row(name, *_exec(runner, argv)))
        return rows + _debate(runner, home, root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def render(rows):
    lines = [f"{'PASS' if r['ok'] else 'FAIL'}  {r['name']}" + ("" if r["ok"] else f"  (exit {r['code']}: {r['tail'][0][:100]})")
             for r in rows]
    bad = [r for r in rows if not r["ok"]]
    return "\n".join(lines + ["", "ALL PASSED" if not bad else f"{len(bad)} FAILED"])
