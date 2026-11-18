"""One command, one proof file: tests, guard score, outbound stop, ledger chain and the numbers page (rule 1).

Nothing here calls a model. Every line states what was run and what came out, so the file can be linked as proof.
"""
import datetime as dt
import subprocess
import sys
from pathlib import Path

from . import canary, numbers, verify


def _tests():
    root = Path(__file__).resolve().parent.parent
    if not (root / "tests").is_dir():
        return {"name": "tests", "ok": True, "detail": "skipped: no tests folder next to this install"}
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x"], cwd=root, capture_output=True, text=True)
    last = (proc.stdout.strip().splitlines() or ["no output"])[-1]
    return {"name": "tests", "ok": proc.returncode == 0, "detail": last}


def run(home, run_tests=True, today=None, commands=None):
    checks = []
    if run_tests:
        checks.append(_tests())
    score = canary.guard_score()
    checks.append({"name": "guard score", "ok": score["blocked"] == score["total"] and not score["benign_flagged"],
                   "detail": f"{score['blocked']} of {score['total']} fake identifiers blocked, "
                             f"{len(score['benign_flagged'])} of {score['benign_total']} harmless texts flagged"})
    out = canary.outbound_check()
    checks.append({"name": "outbound stop", "ok": bool(out["ok"]),
                   "detail": f"{out['kinds_stopped']} of {out['kinds_total']} kinds stopped before sending, "
                             f"{out['model_calls']} model calls, {len(out['leaked_into_logs'])} log leaks"})
    chain = verify.verify_chain(home)
    checks.append({"name": "ledger chain", "ok": chain["ok"],
                   "detail": f"{chain['records']} records, {chain['chained']} chained, {chain['legacy']} older, "
                             f"{len(chain['errors'])} errors, head {chain['head'][:12]}"})
    return {"date": (today or dt.date.today()).isoformat(), "ok": all(c["ok"] for c in checks), "checks": checks,
            "numbers": numbers.render(numbers.build(home, commands), today)}


def render(out):
    lines = [f"# Proof · {out['date']} · {'PASS' if out['ok'] else 'FAIL'}", "", "| Check | Result | What came out |", "|---|---|---|"]
    lines += [f"| {c['name']} | {'pass' if c['ok'] else 'FAIL'} | {c['detail']} |" for c in out["checks"]]
    return "\n".join(lines) + "\n\n" + out["numbers"]
