"""`lifeos pipeline NAME`: a saved flow of lifeos commands with gates. Dry run by default; `--run` executes.

A pipeline is `pipelines/NAME.json` in your home: {"steps": [{"name": ..., "argv": [...], "gate": "stop"|"continue"}]}.
Each step is a normal lifeos command, run through the CLI's own entry point (the runner is passed in), so every
safety check of that command still applies. The default gate is "stop": a failing step skips the rest. Pipelines
cannot nest and cannot hold private data in their arguments (rule 9).
"""
import json
import os
import re
from pathlib import Path

from . import guard

NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")


class PipelineError(Exception):
    pass


def load(home, name):
    if not NAME.match(name or ""):
        raise PipelineError("Pipeline name: lowercase letters, digits, - and _ only.")
    path = Path(home) / "pipelines" / f"{name}.json"
    if not path.exists():
        raise PipelineError(f"No pipeline '{name}' in {path.parent}.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as err:
        raise PipelineError(f"{path.name} is not valid JSON: {err}")
    steps = data.get("steps") if isinstance(data, dict) else None
    if not steps:
        raise PipelineError(f"{name} has no steps.")
    for i, step in enumerate(steps, 1):
        argv = step.get("argv") if isinstance(step, dict) else None
        if not (isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv)):
            raise PipelineError(f"Step {i}: argv must be a list of strings.")
        if argv[0] == "pipeline":
            raise PipelineError(f"Step {i}: pipelines cannot nest.")
        if any(f[1] == "BLOCK" for f in guard.scan_text(" ".join(argv))):
            raise PipelineError(f"Step {i}: the arguments look like private data (rule 9).")
        step.setdefault("name", argv[0])
        step.setdefault("gate", "stop")
    return steps


def run(home, name, runner, execute=False):
    steps = load(home, name)
    rows, halted = [], False
    here = os.getcwd()
    if execute:
        os.chdir(home)  # relative paths in a step (guard now.md) mean files in your home
    try:
        return _go(home, steps, runner, execute, rows, halted)
    finally:
        os.chdir(here)


def _go(home, steps, runner, execute, rows, halted):
    for step in steps:
        row = {"name": step["name"], "argv": step["argv"], "gate": step["gate"]}
        if halted:
            row["status"] = "skipped"
        elif not execute:
            row["status"] = "planned"
        else:
            code = runner(["--home", str(home)] + step["argv"])
            row["status"] = "ok" if code == 0 else "failed"
            halted = code != 0 and step["gate"] == "stop"
        rows.append(row)
    return rows


def render(rows, execute):
    lines = [f"{r['status']:8} {r['name']}  ({' '.join(r['argv'])})" for r in rows]
    if not execute:
        lines.append("\nDry run: nothing was executed. Add --run to execute.")
    return "\n".join(lines)
