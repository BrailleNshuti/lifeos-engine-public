"""Run the full test suite N times with LIFEOS_REPLACE_DIAG set and print recovered against failed counts.

Usage: python scripts/soak.py [--runs 3] [--cmd "python -m pytest -q"] [--diag FILE]
Standard library only. Exit code is 0 when every run passed, 1 otherwise.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def count_events(path):
    """Count `os.replace recovered` and `os.replace failed` lines in a diagnostics file; junk lines are skipped."""
    counts = {"recovered": 0, "failed": 0}
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return counts
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = event.get("event", "") if isinstance(event, dict) else ""
        for kind in counts:
            if name == f"os.replace {kind}":
                counts[kind] += 1
    return counts


def summary(runs):
    passed = sum(1 for r in runs if r["code"] == 0)
    rec = sum(r["recovered"] for r in runs)
    fail = sum(r["failed"] for r in runs)
    return f"{len(runs)} runs, {passed} passed, os.replace recovered {rec}, failed {fail}"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--cmd", default=f'"{sys.executable}" -m pytest -q')
    p.add_argument("--diag", help="diagnostics file (default: a temporary file)")
    a = p.parse_args(argv)
    diag = Path(a.diag) if a.diag else Path(tempfile.mkdtemp(prefix="soak-")) / "diag.jsonl"
    runs = []
    for n in range(1, a.runs + 1):
        before = count_events(diag)
        env = {**os.environ, "LIFEOS_REPLACE_DIAG": str(diag)}
        code = subprocess.run(a.cmd, shell=True, env=env).returncode
        after = count_events(diag)
        run = {"code": code, "recovered": after["recovered"] - before["recovered"], "failed": after["failed"] - before["failed"]}
        runs.append(run)
        print(f"run {n}: exit {code}, recovered {run['recovered']}, failed {run['failed']}")
    print(summary(runs))
    return 0 if all(r["code"] == 0 for r in runs) else 1


if __name__ == "__main__":
    sys.exit(main())
