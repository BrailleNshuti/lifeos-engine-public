"""lifeos ask: send a task's context pack to another model and write the answer back into the task file.

Adapters are small functions (prompt in, text out). The privacy guard runs on the pack first; a BLOCK stops the call.
Prompts go in through stdin, never as arguments, so they stay out of the process list.
"""
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request

from .check import check_answer
from .context import task_file, build_pack
from .guard import private_patterns, scan_text
from .store import model_call_note, record_result

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


MAX_ARG_CHARS = 30000  # Windows allows about 32,767 characters on a command line


def _run_cli(cmd, prompt, timeout=TIMEOUT, via_stdin=True):
    exe = shutil.which(cmd[0])  # finds codex.cmd and friends on Windows
    if not exe:
        raise ToolMissing(f"{cmd[0]} is not installed or not on PATH.")
    try:  # an empty temp folder: the model sees the pack and nothing else on disk
        with tempfile.TemporaryDirectory() as empty:
            done = subprocess.run([exe, *cmd[1:]], input=prompt if via_stdin else None,
                                  stdin=None if via_stdin else subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout,
                                  encoding="utf-8", errors="replace", cwd=empty)
    except subprocess.TimeoutExpired:
        raise AskError(f"{cmd[0]} timed out after {timeout} s.") from None
    if done.returncode != 0:
        raise AskError(f"{cmd[0]} failed: {done.stderr.strip()[:300]}")
    return done.stdout.strip()


def ask_codex(prompt):
    return _run_cli(["codex", "exec", "--skip-git-repo-check", "-s", "read-only", "-"], prompt)


def ask_gemini(prompt):
    """Gemini through Antigravity (agy): Google ended Gemini CLI sign-in for individuals. agy ignores stdin."""
    if len(prompt) > MAX_ARG_CHARS:
        raise AskError(f"The pack is {len(prompt)} characters; agy takes the prompt as an argument (limit {MAX_ARG_CHARS}). "
                       "Use a smaller --budget.")
    return _run_cli(["agy", "--sandbox", "-p", prompt], prompt, via_stdin=False)


def ask_claude(prompt):
    return _run_cli(["claude", "-p", "--model", "sonnet"], prompt)


def _open_local(req, timeout):
    """Open a request to the local model. The system proxy is bypassed: prompt text never leaves this computer."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout)


def ollama_host():
    """Return the configured loopback Ollama URL, refusing remote hosts."""
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    if "://" not in host:
        host = "http://" + host
    name = urllib.parse.urlparse(host).hostname
    if name not in ("localhost", "127.0.0.1", "::1"):
        raise Blocked(f"OLLAMA_HOST points to '{name}'. local-model tasks may only use Ollama on this computer.")
    return host.rstrip("/")


def ollama_generate(prompt, model, options=None):
    host = ollama_host()
    payload = {"model": model, "prompt": prompt, "stream": False}
    if options:
        payload["options"] = options
    body = json.dumps(payload).encode()
    req = urllib.request.Request(f"{host}/api/generate", data=body, headers={"Content-Type": "application/json"})
    try:
        with _open_local(req, TIMEOUT) as resp:
            text = json.loads(resp.read())["response"]
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise ToolMissing(f"ollama has no model '{model}'. Run: ollama pull {model}") from None
        raise AskError(f"ollama returned HTTP {error.code}.") from None
    except TimeoutError:
        raise AskError(f"ollama did not answer within {TIMEOUT} s (a slow or busy model, not a missing tool).") from None
    except OSError as error:
        raise ToolMissing(f"ollama is not reachable at {host}: {error}") from None
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()  # reasoning models: keep the answer only


def ask_ollama(prompt):
    return ollama_generate(prompt, os.environ.get("LIFEOS_OLLAMA_MODEL", "llama3.2"))


def ask_qwen(prompt):
    """Qwen through Ollama, local and private. Change the size with LIFEOS_QWEN_MODEL."""
    return ollama_generate(prompt, qwen_model())


def qwen_model():
    return os.environ.get("LIFEOS_QWEN_MODEL", "qwen2.5:3b")


def label(model):
    """Name written into the result header; Ollama shows which local model answered."""
    if model == "ollama":
        return "ollama:" + os.environ.get("LIFEOS_OLLAMA_MODEL", "llama3.2")
    if model == "qwen":
        return "qwen:" + qwen_model()
    return model


ADAPTERS = {"codex": ask_codex, "gemini": ask_gemini, "claude": ask_claude, "ollama": ask_ollama, "qwen": ask_qwen}


def check_text(text, where, action):
    # The allow marker is for reviewed repository files. Untrusted prompts and
    # model answers may not exempt themselves from the boundary check.
    blocks = [f for f in scan_text(text, private_patterns(), allow_mark=False) if f[1] == "BLOCK"]
    if blocks:
        kinds = ", ".join(sorted({f[2] for f in blocks}))
        raise Blocked(f"{len(blocks)} high-confidence sensitive finding(s) in {where} ({kinds}). {action}")


def write_result(home, task_id, who, text, today=None, note="written via lifeos mcp"):
    """Append a result written by someone else (a chat, a person) to a task file. The guard checks it first."""
    who = " ".join(str(who).replace(",", " ").split())  # one line, no commas: a name can never add a ledger row or a heading
    check_text(text, "the result", "Nothing was written to your files.")
    path = task_file(home, task_id)
    record_result(home, path, who, text, today or dt.date.today(), note)
    return path


def run_ask(home, model, task_id, budget=6000, dry_run=False, adapters=None, today=None, full=False):
    """Return the task path after writing the answer, or (pack, tokens) for a dry run."""
    adapters = adapters or ADAPTERS
    if model not in adapters:
        raise ValueError(f"Unknown model '{model}'. Choose one of: {', '.join(sorted(adapters))}.")
    pack, tokens = build_pack(home, task_id, budget, task_first=True, names=None if full else MINIMAL)
    check_text(pack, "the context pack", "Nothing was sent.")
    if dry_run:
        return pack, tokens
    path = task_file(home, task_id)
    text = adapters[model](f"{INSTRUCTION}\n\n{pack}")
    check_text(text, "the answer", "Nothing was written to your files.")
    note = model_call_note(len(check_answer(text)))  # the count only: never the answer or the flag texts
    record_result(home, path, label(model), text, today or dt.date.today(), note)
    return path


