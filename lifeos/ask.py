"""lifeos ask: send a task's context pack to another model and write the answer back into the task file.

Adapters are small functions (prompt in, text out). The privacy guard runs on the pack first; a BLOCK stops the call.
Prompts go in through stdin, never as arguments, so they stay out of the process list.
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from .context import _task_file, build_pack
from .guard import _private_patterns, scan_text

TIMEOUT = 600
MINIMAL = ("TASK", "rules.md")  # now.md and me.md only go out with --full
INSTRUCTION = ("You are helping with the task below. Use only the context given. Answer with the result only: "
               "what was done, evidence, open issues, next step. Never ask for class C data (IDs, bank, passwords, health).")


class Blocked(Exception):
    """The guard found class C data in the pack; nothing was sent."""


class AskError(RuntimeError):
    """The model call failed."""


class ToolMissing(FileNotFoundError):
    """The command-line tool for this model is not installed."""


def _run_cli(cmd, prompt, timeout=TIMEOUT):
    exe = shutil.which(cmd[0])  # finds codex.cmd and friends on Windows
    if not exe:
        raise ToolMissing(f"{cmd[0]} is not installed or not on PATH.")
    try:  # an empty temp folder: the model sees the pack and nothing else on disk
        with tempfile.TemporaryDirectory() as empty:
            done = subprocess.run([exe, *cmd[1:]], input=prompt, capture_output=True, text=True, timeout=timeout,
                                  encoding="utf-8", errors="replace", cwd=empty)
    except subprocess.TimeoutExpired:
        raise AskError(f"{cmd[0]} timed out after {timeout} s.") from None
    if done.returncode != 0:
        raise AskError(f"{cmd[0]} failed: {done.stderr.strip()[:300]}")
    return done.stdout.strip()


def ask_codex(prompt):
    return _run_cli(["codex", "exec", "--skip-git-repo-check", "-s", "read-only", "-"], prompt)


def ask_gemini(prompt):
    return _run_cli(["gemini", "-p", "Follow the instruction and task given on stdin."], prompt)


def ask_claude(prompt):
    return _run_cli(["claude", "-p", "--model", "sonnet"], prompt)


def ask_ollama(prompt):
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    if "://" not in host:
        host = "http://" + host
    body = json.dumps({"model": os.environ.get("LIFEOS_OLLAMA_MODEL", "llama3.2"), "prompt": prompt,
                       "stream": False}).encode()
    req = urllib.request.Request(f"{host}/api/generate", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read())["response"].strip()
    except OSError as error:
        raise ToolMissing(f"ollama is not reachable at {host}: {error}") from None


ADAPTERS = {"codex": ask_codex, "gemini": ask_gemini, "claude": ask_claude, "ollama": ask_ollama}


def _check(text, where, action):
    blocks = [f for f in scan_text(text, _private_patterns()) if f[1] == "BLOCK"]
    if blocks:
        kinds = ", ".join(sorted({f[2] for f in blocks}))
        raise Blocked(f"{len(blocks)} finding(s) of class C data in {where} ({kinds}). {action}")


def _record(home, path, model, text, today):
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n## Result · {model} · {today:%Y-%m-%d}\n{text}\n")
    ledger = Path(home) / "logs" / "ledger.csv"
    if ledger.exists():
        with open(ledger, "a", encoding="utf-8") as f:
            f.write(f"{today:%Y-%m-%d},{path.stem},{model},,asked via lifeos ask\n")


def run_ask(home, model, task_id, budget=6000, dry_run=False, adapters=None, today=None, full=False):
    """Return the task path after writing the answer, or (pack, tokens) for a dry run."""
    adapters = adapters or ADAPTERS
    if model not in adapters:
        raise ValueError(f"Unknown model '{model}'. Choose one of: {', '.join(sorted(adapters))}.")
    pack, tokens = build_pack(home, task_id, budget, task_first=True, names=None if full else MINIMAL)
    _check(pack, "the context pack", "Nothing was sent.")
    if dry_run:
        return pack, tokens
    path = _task_file(home, task_id)
    text = adapters[model](f"{INSTRUCTION}\n\n{pack}")
    _check(text, "the answer", "Nothing was written to your files.")
    _record(home, path, model, text, today or dt.date.today())
    return path
