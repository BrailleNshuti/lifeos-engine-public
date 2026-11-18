"""`lifeos selftest`: run the commands on a throwaway copy of the demo home and say PASS or FAIL for each.

It never touches your real notes and calls no model. The runner is passed in (the CLI's own `main`), so every step
goes through the same entry point you use. Output of each step is captured; a failing step names itself.
"""
import contextlib
import io
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
            sink = io.StringIO()
            try:
                with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                    code = runner(argv)
            except SystemExit as exit_:
                code = exit_.code if isinstance(exit_.code, int) else 1
            except Exception as err:  # a crash is a FAIL with its type, not a traceback wall
                code, sink = 1, io.StringIO(f"{type(err).__name__}: {err}")
            rows.append({"name": name, "ok": code == 0, "code": code, "tail": sink.getvalue().strip().splitlines()[-1:] or [""]})
        return rows
    finally:
        shutil.rmtree(root, ignore_errors=True)


def render(rows):
    lines = [f"{'PASS' if r['ok'] else 'FAIL'}  {r['name']}" + ("" if r["ok"] else f"  (exit {r['code']}: {r['tail'][0][:100]})")
             for r in rows]
    bad = [r for r in rows if not r["ok"]]
    return "\n".join(lines + ["", "ALL PASSED" if not bad else f"{len(bad)} FAILED"])
