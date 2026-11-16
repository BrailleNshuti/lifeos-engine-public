"""lifeos ask & review: send a task's context pack to models and write guarded results + durable run records.

Adapters are small functions (prompt in, text out). The privacy guard runs on the pack first; a BLOCK stops the call.
Prompts go in through stdin, never as arguments, so they stay out of the process list.
"""
from contextlib import contextmanager
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .check import check_answer
from .context import build_pack, build_review_pack, inspect_repo_commit, pack_hash, task_file, visible_task
from .seats import focus_error
from .guard import (
    CARD_CANDIDATE, EMAIL, IBAN_CANDIDATE, ID_DOCUMENT, PHONE,
    SECRET_ASSIGNMENT, TOKEN_PATTERNS, iban_valid, luhn_valid, private_patterns, scan_text,
)
from .policy import check_provider_allowed, classify_content
from .store import (
    RUN_SCHEMA_VERSION, append_run_record, get_run_record, has_run_id, is_valid_git_oid,
    model_call_note, new_run_id, record_result, run_lock, utc_now_iso, validate_run_id,
)

TIMEOUT = 600
PROBE_TIMEOUT = 3
MINIMAL = ("TASK", "rules.md")  # now.md and me.md only go out with --full
INSTRUCTION = ("You are helping with the task below. Use only the context given. Answer with the result only: "
               "what was done, evidence, open issues, next step. Never ask for class C data (IDs, bank, passwords, health).")
REVIEW_INSTRUCTION = ("You are conducting an independent blind review (rule 7). You see only the task facts, rules, "
                      "and any supplied repository commit/diff—never another model's answer. List findings in priority "
                      "order (bugs, missing tests, privacy or security problems, rule violations), evidence, and the "
                      "exact fix or verdict. End with Next step.")

_REVIEW_TLS = threading.local()


class Blocked(Exception):
    """The guard found class C data in the pack; nothing was sent."""


class AskError(RuntimeError):
    """The model call failed."""

    def __init__(self, message, run_id=None):
        super().__init__(message)
        self.run_id = run_id


class ToolMissing(FileNotFoundError):
    """The command-line tool for this model is not installed."""

    def __init__(self, message, run_id=None):
        super().__init__(message)
        self.run_id = run_id


def task_data_tier(path):
    """Classify task facts for execution policy without considering prior model answers or route notes."""
    raw = visible_task(Path(path).read_text(encoding="utf-8"))
    facts = re.split(r"^## Result.*$", raw, maxsplit=1, flags=re.MULTILINE)[0]
    return classify_content(facts, f"tasks/{Path(path).name}")


def enforce_task_policy(path, model, full=False):
    """Return the task tier or block a provider that is unsafe for that tier."""
    tier = task_data_tier(path)
    if model not in PROVIDERS:  # injected test/private adapters have no declared locality contract
        return tier
    allowed, reason = check_provider_allowed(tier, model, full=full)
    if not allowed:
        raise Blocked(f"Provider policy blocked this task: {reason}")
    return tier


def current_review_cwd():
    """Return the active isolated git worktree Path during a repository review, or None."""
    return getattr(_REVIEW_TLS, "cwd", None)


@contextmanager
def _isolated_git_worktree(repo_info):
    """Create a temporary detached git worktree at repo_info['commit_sha'] for read-only inspection."""
    if not repo_info:
        yield None
        return
    repo = Path(repo_info["repo"])
    commit_sha = repo_info["commit_sha"]
    parent_tmp = Path(tempfile.mkdtemp(prefix="lifeos-review-wt-"))
    wt_dir = parent_tmp / repo.name
    try:
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "add", "--detach", str(wt_dir), commit_sha],
            capture_output=True, text=True, check=True,
        )
        prev = getattr(_REVIEW_TLS, "cwd", None)
        _REVIEW_TLS.cwd = wt_dir
        try:
            yield wt_dir
        finally:
            _REVIEW_TLS.cwd = prev
    finally:
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "remove", "--force", str(wt_dir)],
            capture_output=True, text=True, check=False,
        )
        shutil.rmtree(parent_tmp, ignore_errors=True)


def _child_env():
    """Ensure the active Python interpreter and its Scripts/bin directory are on PATH for child CLI subprocesses."""
    env = os.environ.copy()
    py_dir = Path(sys.executable).resolve().parent
    scripts_dir = py_dir / ("Scripts" if os.name == "nt" else "bin")
    prepend = [str(d) for d in (scripts_dir, py_dir) if d.is_dir()]
    cur_path = env.get("PATH", "")
    env["PATH"] = os.pathsep.join(prepend + ([cur_path] if cur_path else []))
    return env


def _run_cli(cmd, prompt, timeout=TIMEOUT, via_stdin=True, use_review_cwd=True):
    exe = shutil.which(cmd[0])  # finds codex.cmd and friends on Windows
    if not exe:
        raise ToolMissing(f"{cmd[0]} is not installed or not on PATH.")
    active_cwd = current_review_cwd() if use_review_cwd else None
    env = _child_env()
    try:
        if active_cwd is not None:
            done = subprocess.run(
                [exe, *cmd[1:]], input=prompt if via_stdin else None,
                stdin=None if via_stdin else subprocess.DEVNULL, capture_output=True, text=True,
                timeout=timeout, encoding="utf-8", errors="replace", cwd=str(active_cwd), env=env,
            )
        else:
            # An empty temp folder: the model sees the pack and nothing else on disk
            with tempfile.TemporaryDirectory() as empty:
                done = subprocess.run(
                    [exe, *cmd[1:]], input=prompt if via_stdin else None,
                    stdin=None if via_stdin else subprocess.DEVNULL, capture_output=True, text=True,
                    timeout=timeout, encoding="utf-8", errors="replace", cwd=empty, env=env,
                )
    except subprocess.TimeoutExpired:
        raise AskError(f"{cmd[0]} timed out after {timeout} s.") from None
    if done.returncode != 0:
        raise AskError(f"{cmd[0]} failed: {redact_error(done.stderr)}")
    return done.stdout.strip()


def ask_codex(prompt):
    return _run_cli(["codex", "exec", "--skip-git-repo-check", "-s", "read-only", "-"], prompt)


def _parse_agy_stream_json(raw):
    """Parse Antigravity stream-json NDJSON output and return the final model response text."""
    lines = [line.strip() for line in (raw or "").splitlines() if line.strip()]
    if not lines:
        raise AskError("agy failed: empty stream-json output.")
    terminal_response = None
    for line in lines:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            raise AskError("agy failed: malformed stream-json output.") from None
        if not isinstance(obj, dict) or not isinstance(obj.get("event"), str):
            raise AskError("agy failed: malformed stream-json event.")
        if obj["event"] == "result":
            res = obj.get("result")
            if not isinstance(res, dict):
                raise AskError("agy failed: malformed stream-json result payload.")
            status = str(res.get("status") or "").upper()
            err_msg = res.get("error")
            if status != "SUCCESS" or err_msg:
                detail = redact_error(err_msg) if err_msg else f"status {status or 'UNKNOWN'}"
                raise AskError(f"agy failed: {detail}")
            text = str(res.get("response") or "").strip()
            if not text:
                raise AskError("agy failed: empty response in stream-json result.")
            terminal_response = text
    if terminal_response is None:
        raise AskError("agy failed: missing terminal result event in stream-json output.")
    return terminal_response


def ask_gemini(prompt):
    """Gemini through Antigravity (agy) stream-json stdin mode in an isolated empty temp directory."""
    payload = json.dumps({
        "event": "user",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": prompt}],
        },
    }, ensure_ascii=False) + "\n"
    raw = _run_cli(
        [
            "agy", "--sandbox", "--disable-slash-commands",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--print=",
        ],
        payload,
        via_stdin=True,
        use_review_cwd=False,
    )
    return _parse_agy_stream_json(raw)


def ask_claude(prompt):
    # Automated repository review must not trust project instructions, plugins,
    # MCP servers, hooks, or mutation-capable tools from the reviewed worktree.
    return _run_cli([
        "claude", "-p", "--model", "sonnet",
        "--safe-mode", "--restricted", "--tools", "Read,Glob,Grep",
        "--strict-mcp-config", "--no-session-persistence",
        "--permission-prompts", "none",
    ], prompt)


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
        raise ToolMissing(f"ollama is not reachable at {host}: {redact_error(error)}") from None
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()  # reasoning models: keep the answer only


def ask_ollama(prompt):
    return ollama_generate(prompt, os.environ.get("LIFEOS_OLLAMA_MODEL", "llama3.2"))


def ask_qwen(prompt):
    """Qwen through Ollama, local and private. Change the size with LIFEOS_QWEN_MODEL."""
    return ollama_generate(prompt, qwen_model())


def qwen_model():
    return os.environ.get("LIFEOS_QWEN_MODEL", "qwen3.5:4b")


def label(model):
    """Name written into the result header; Ollama shows which local model answered."""
    if model == "ollama":
        return "ollama:" + os.environ.get("LIFEOS_OLLAMA_MODEL", "llama3.2")
    if model == "qwen":
        return "qwen:" + qwen_model()
    return model


ADAPTERS = {"codex": ask_codex, "gemini": ask_gemini, "claude": ask_claude, "ollama": ask_ollama, "qwen": ask_qwen}
PROVIDERS = {
    "claude": {
        "locality": "remote", "binary": "claude",
        "capabilities": {"input": "stdin", "sandbox": "cli", "worktree_review": True},
    },
    "codex": {
        "locality": "remote", "binary": "codex",
        "capabilities": {"input": "stdin", "sandbox": "read-only", "worktree_review": True},
    },
    "gemini": {
        "locality": "remote", "binary": "agy",
        "capabilities": {"input": "stdin", "sandbox": "sandbox-flag", "worktree_review": False},
    },
    "ollama": {
        "locality": "local", "binary": "ollama",
        "capabilities": {"input": "http-loopback", "sandbox": "local-only", "worktree_review": False},
    },
    "qwen": {
        "locality": "local", "binary": "ollama",
        "capabilities": {"input": "http-loopback", "sandbox": "local-only", "worktree_review": False},
    },
}


def _probe_ollama_tags():
    """Fetch installed model names from local Ollama /api/tags, or None if unreachable."""
    try:
        host = ollama_host()
        req = urllib.request.Request(f"{host}/api/tags")
        with _open_local(req, PROBE_TIMEOUT) as resp:
            data = json.loads(resp.read())
        return {m.get("name", "") for m in data.get("models", [])}
    except Exception:
        return None


def provider_status(probe=False, smoke=False, adapters=None):
    """Return availability, capability contract and (when probe=True or smoke=True) live health status for each provider."""
    rows = []
    active_adapters = adapters or ADAPTERS
    tags = _probe_ollama_tags() if (probe or smoke) else None
    for name, info in sorted(PROVIDERS.items()):
        exe = shutil.which(info["binary"])
        available = bool(exe)
        status = "available" if available else "missing"
        detail = info["binary"]
        if smoke:
            if name in ("ollama", "qwen"):
                target = qwen_model() if name == "qwen" else os.environ.get("LIFEOS_OLLAMA_MODEL", "llama3.2")
                detail = f"ollama ({target})"
                if tags is None and adapters is None:
                    status = "unreachable"
                elif tags is not None and target not in tags and f"{target}:latest" not in tags and adapters is None:
                    status = "model_missing"
                else:
                    try:
                        ans = active_adapters[name]("Reply with OK only.")
                        status = "healthy" if ans else "unhealthy"
                        detail = f"ollama ({target}, smoke ok)" if ans else f"ollama ({target}, empty smoke response)"
                    except Exception:
                        status = "unhealthy"
                        detail = f"ollama ({target}, smoke failed)"
            elif not available and adapters is None:
                status = "missing"
            else:
                try:
                    ans = active_adapters[name]("Reply with OK only.")
                    status = "healthy" if ans else "unhealthy"
                    detail = f"{info['binary']} (smoke ok)" if ans else f"{info['binary']} (empty smoke response)"
                except Exception:
                    status = "unhealthy"
                    detail = f"{info['binary']} (smoke failed)"
        elif probe:
            if name in ("ollama", "qwen"):
                target = qwen_model() if name == "qwen" else os.environ.get("LIFEOS_OLLAMA_MODEL", "llama3.2")
                detail = f"ollama ({target})"
                if tags is None:
                    status = "unreachable"
                elif target in tags or f"{target}:latest" in tags:
                    status = "healthy"
                else:
                    status = "model_missing"
            elif not available:
                status = "missing"
            else:
                try:
                    done = subprocess.run(
                        [exe, "--version"], capture_output=True, text=True, timeout=PROBE_TIMEOUT,
                        encoding="utf-8", errors="replace",
                    )
                    if done.returncode == 0:
                        status = "cli_healthy"
                        detail = f"{info['binary']} (--version ok)"
                    else:
                        status = "unhealthy"
                except Exception:
                    status = "unreachable"
        rows.append({
            "model": name,
            "locality": info["locality"],
            "binary": info["binary"],
            "available": available,
            "status": status,
            "detail": detail,
            "capabilities": dict(info["capabilities"]),
        })
    return rows


def redact_error(text):
    """Redact any secret, token, ID, financial identifier, contact detail, or private pattern from an error string."""
    msg = " ".join(str(text or "").splitlines()).strip()
    for _, pat in TOKEN_PATTERNS:
        msg = pat.sub("[REDACTED]", msg)
    msg = SECRET_ASSIGNMENT.sub("[REDACTED]", msg)
    msg = ID_DOCUMENT.sub(
        lambda m: "[REDACTED]" if any(c.isdigit() for c in m.group(1)) else m.group(0), msg
    )
    msg = IBAN_CANDIDATE.sub(lambda m: "[REDACTED]" if iban_valid(m.group(0)) else m.group(0), msg)
    msg = CARD_CANDIDATE.sub(lambda m: "[REDACTED]" if luhn_valid(m.group(0)) else m.group(0), msg)
    msg = EMAIL.sub("[REDACTED]", msg)
    msg = PHONE.sub("[REDACTED]", msg)
    for pat in private_patterns():
        msg = pat.sub("[REDACTED]", msg)
    if any(f[1] == "BLOCK" for f in scan_text(msg, private_patterns(), allow_mark=False)):
        return "[REDACTED sensitive error]"
    return focus_error(msg)[:240]


def _classify_ask_error(error):
    low = str(error).lower()
    if "timed out" in low or "did not answer within" in low:
        return "timeout"
    return "failed"


def check_text(text, where, action):
    # The allow marker is for reviewed repository files. Untrusted prompts and
    # model answers may not exempt themselves from the boundary check.
    blocks = [f for f in scan_text(text, private_patterns(), allow_mark=False) if f[1] == "BLOCK"]
    if blocks:
        kinds = ", ".join(sorted({f[2] for f in blocks}))
        raise Blocked(f"{len(blocks)} high-confidence sensitive finding(s) in {where} ({kinds}). {action}")


def write_result(home, task_id, who, text, today=None, note="written via lifeos mcp", run_id=None):
    """Append a result written by someone else (a chat, a person) to a task file. The guard checks it first."""
    who = " ".join(str(who).replace(",", " ").split())  # one line, no commas: a name can never add a ledger row or a heading
    check_text(text, "the result", "Nothing was written to your files.")
    path = task_file(home, task_id)
    record_result(home, path, who, text, today or dt.date.today(), note, run_id=run_id)
    return path


def _reconstruct_persisted_error(home, rec):
    """Re-raise the terminal exception corresponding to a persisted non-ok run record."""
    status = rec.get("status")
    msg = rec.get("error") or f"persisted run {rec.get('run_id')} terminated with status {status}"
    if status == "tool_missing":
        return ToolMissing(msg)
    if status == "blocked":
        return Blocked(msg)
    if status in ("partial", "failed"):
        for cid in rec.get("child_run_ids") or ():
            child = get_run_record(home, cid, normalize=True)
            if child and child.get("status") != "ok":
                return _reconstruct_persisted_error(home, child)
    return AskError(msg)


def _valid_persisted_budget(val):
    return not isinstance(val, bool) and isinstance(val, int) and 1 <= val <= 50000


def _verify_ask_identity(rec, task_stem, expected_model, budget=6000, full=False, parent_run_id=None):
    """Ensure a reused run_id matches the original ask command, task_id, model, budget, full flag, and parent_run_id.
    Schema v2 records require all identity fields to be present; legacy v1 records default conservatively to (6000, False, None)."""
    if (
        rec.get("command") != "ask"
        or rec.get("task_id") != task_stem
        or rec.get("model") != expected_model
    ):
        raise ValueError(
            f"run_id '{rec.get('run_id')}' already belongs to a different operation "
            f"({rec.get('command')}:{rec.get('task_id')}:{rec.get('model')})."
        )
    is_v2 = int(rec.get("schema_version", 1)) >= 2
    if is_v2 and any(k not in rec for k in ("budget", "full", "parent_run_id")):
        raise ValueError(
            f"run_id '{rec.get('run_id')}' is missing mandatory v2 ask identity fields."
        )
    rec_budget = rec.get("budget") if is_v2 else rec.get("budget", 6000)
    if not _valid_persisted_budget(rec_budget) or rec_budget != budget:
        raise ValueError(
            f"run_id '{rec.get('run_id')}' already belongs to budget {rec_budget!r} (got {budget})."
        )
    rec_full = rec.get("full") if is_v2 else rec.get("full", False)
    if not isinstance(rec_full, bool) or rec_full != bool(full):
        raise ValueError(
            f"run_id '{rec.get('run_id')}' already belongs to full={rec_full} (got {bool(full)})."
        )
    rec_parent = rec.get("parent_run_id") if is_v2 else rec.get("parent_run_id", None)
    if rec_parent != parent_run_id:
        raise ValueError(
            f"run_id '{rec.get('run_id')}' already belongs to parent_run_id '{rec_parent}'."
        )


def _diff_digest(diff_text):
    return pack_hash(diff_text) if (diff_text and diff_text.strip()) else None


def _normalize_repo_and_commit(repo, commit):
    """Validate and normalize (repo, commit) once before execution or identity verification."""
    if repo is None:
        return None, None
    if not isinstance(repo, (str, Path)) or not str(repo).strip():
        raise ValueError("repo must be a non-empty path or None.")
    if not isinstance(commit, str) or not commit.strip():
        raise ValueError("commit must be a non-empty string when repo is set.")
    return repo, commit.strip()


def _verify_review_identity(rec, task_stem, expected_model, repo, commit, budget=6000, diff_text=""):
    """Ensure a reused run_id matches the original review_group command, task_id, reviewers, budget, diff_sha256, repo,
    and literal requested_commit without inspecting Git or reopening the repository.
    Schema v2 records require all identity fields to be present; legacy v1 records default conservatively."""
    if (
        rec.get("command") != "review_group"
        or rec.get("task_id") != task_stem
        or rec.get("model") != expected_model
    ):
        raise ValueError(
            f"run_id '{rec.get('run_id')}' already belongs to a different operation "
            f"({rec.get('command')}:{rec.get('task_id')}:{rec.get('model')})."
        )
    is_v2 = int(rec.get("schema_version", 1)) >= 2
    if is_v2 and any(k not in rec for k in ("budget", "diff_sha256", "requested_commit", "repo", "commit_sha")):
        raise ValueError(
            f"run_id '{rec.get('run_id')}' is missing mandatory v2 review identity fields."
        )
    rec_budget = rec.get("budget") if is_v2 else rec.get("budget", 6000)
    if not _valid_persisted_budget(rec_budget) or rec_budget != budget:
        raise ValueError(
            f"run_id '{rec.get('run_id')}' already belongs to budget {rec_budget!r} (got {budget})."
        )
    expected_diff_sha = _diff_digest(diff_text)
    rec_diff_sha = rec.get("diff_sha256") if is_v2 else rec.get("diff_sha256", None)
    if rec_diff_sha != expected_diff_sha:
        raise ValueError(
            f"run_id '{rec.get('run_id')}' already belongs to a different diff_text."
        )
    norm_repo, req_arg = _normalize_repo_and_commit(repo, commit)
    rec_repo = rec.get("repo")
    rec_req = rec.get("requested_commit")
    rec_sha = rec.get("commit_sha")
    if norm_repo is None:
        if rec_repo is not None:
            raise ValueError(f"run_id '{rec.get('run_id')}' already belongs to a different repository setting.")
        if rec_req is not None:
            raise ValueError(f"run_id '{rec.get('run_id')}' already belongs to commit '{rec_req}'.")
        if rec_sha is not None:
            raise ValueError(f"run_id '{rec.get('run_id')}' already belongs to commit '{rec_sha}'.")
    else:
        if not isinstance(rec_repo, str) or not rec_repo.strip():
            raise ValueError(f"run_id '{rec.get('run_id')}' already belongs to a different repository setting.")
        if Path(norm_repo).resolve() != Path(rec_repo).resolve():
            raise ValueError(f"run_id '{rec.get('run_id')}' already belongs to repository '{rec_repo}'.")
        if is_v2:
            if not isinstance(rec_req, str) or not rec_req.strip() or req_arg != rec_req:
                raise ValueError(
                    f"run_id '{rec.get('run_id')}' already belongs to commit '{rec_req}'."
                )
            allow_null_sha = rec.get("status") == "failed"
            if rec_sha is None:
                if not allow_null_sha:
                    raise ValueError(f"run_id '{rec.get('run_id')}' is missing commit_sha for repository review.")
            elif not is_valid_git_oid(rec_sha):
                raise ValueError(f"run_id '{rec.get('run_id')}' has invalid commit_sha '{rec_sha}'.")
        else:
            if rec_req is not None:
                if not isinstance(rec_req, str) or not rec_req.strip() or req_arg != rec_req:
                    raise ValueError(
                        f"run_id '{rec.get('run_id')}' already belongs to commit '{rec_req}'."
                    )
            elif rec_sha is not None and (
                not is_valid_git_oid(rec_sha) or req_arg not in ("HEAD", rec_sha)
            ):
                raise ValueError(f"run_id '{rec.get('run_id')}' already belongs to commit '{rec_sha}'.")


def _verify_review_child_identity(
    child_rec, group_id, task_stem, who, digest, repo_label, commit_sha, req_commit, budget=6000, diff_sha=None
):
    """Ensure a persisted child review record from an interrupted run matches the parent, task, model, context digest,
    budget, diff_sha256, repo, and commit."""
    is_v2 = int(child_rec.get("schema_version", 1)) >= 2
    req_child_keys = (
        "budget", "diff_sha256", "requested_commit", "parent_run_id", "context_sha256", "repo", "commit_sha"
    )
    if is_v2 and any(k not in child_rec for k in req_child_keys):
        raise ValueError(
            f"child run_id '{child_rec.get('run_id')}' is missing mandatory v2 review identity fields."
        )
    rec_budget = child_rec.get("budget") if is_v2 else child_rec.get("budget", 6000)
    rec_diff_sha = child_rec.get("diff_sha256") if is_v2 else child_rec.get("diff_sha256", None)
    rec_repo = child_rec.get("repo")
    rec_req = child_rec.get("requested_commit")
    rec_sha = child_rec.get("commit_sha")
    if repo_label is None:
        repo_ok = rec_repo is None and rec_req is None and rec_sha is None
    else:
        repo_ok = (
            isinstance(rec_repo, str)
            and bool(rec_repo.strip())
            and Path(rec_repo).resolve() == Path(repo_label).resolve()
            and isinstance(rec_req, str)
            and bool(rec_req.strip())
            and rec_req == req_commit
            and is_valid_git_oid(rec_sha)
            and rec_sha == commit_sha
        )
    if (
        child_rec.get("command") != "review"
        or child_rec.get("parent_run_id") != group_id
        or child_rec.get("task_id") != task_stem
        or child_rec.get("model") != who
        or child_rec.get("context_sha256") != digest
        or not repo_ok
        or not _valid_persisted_budget(rec_budget)
        or rec_budget != budget
        or rec_diff_sha != diff_sha
    ):
        raise ValueError(
            f"child run_id '{child_rec.get('run_id')}' already belongs to a different context or commit."
        )


def run_ask(home, model, task_id, budget=6000, dry_run=False, adapters=None, today=None, full=False,
            parent_run_id=None, run_id=None):
    """Return the task path after writing the answer, or (pack, tokens) for a dry run."""
    adapters = adapters or ADAPTERS
    if model not in adapters:
        raise ValueError(f"Unknown model '{model}'. Choose one of: {', '.join(sorted(adapters))}.")
    path = task_file(home, task_id)
    day = today or dt.date.today()
    rid = validate_run_id(run_id) if run_id is not None else new_run_id(day)
    expected_model = label(model)

    with run_lock(home if not dry_run else None, rid):
        if not dry_run:
            existing = get_run_record(home, rid, normalize=True)
            if existing is not None:
                _verify_ask_identity(existing, path.stem, expected_model, budget=budget, full=full, parent_run_id=parent_run_id)
                if existing.get("status") == "ok":
                    return path
                raise _reconstruct_persisted_error(home, existing)

        started_iso = utc_now_iso()
        pack, tokens = build_pack(home, task_id, budget, task_first=True, names=None if full else MINIMAL)
        digest = pack_hash(pack)
        locality = PROVIDERS.get(model, {}).get("locality", "remote")
        base_rec = {
            "schema_version": RUN_SCHEMA_VERSION, "run_id": rid, "parent_run_id": parent_run_id,
            "date": day.isoformat(), "started_at": started_iso, "command": "ask",
            "task_id": path.stem, "model": expected_model, "locality": locality,
            "context_sha256": digest, "tokens": tokens, "budget": budget, "full": bool(full), "terminal": True,
        }
        try:
            check_text(pack, "the context pack", "Nothing was sent.")
        except Blocked as err:
            if not dry_run:
                append_run_record(home, {
                    **base_rec, "finished_at": utc_now_iso(), "duration_ms": 0, "status": "blocked",
                    "phase": "outbound_context", "flags": 0, "error": redact_error(err),
                })
            raise
        try:
            base_rec["data_tier"] = enforce_task_policy(path, model, full=full)
        except Blocked as err:
            if not dry_run:
                append_run_record(home, {
                    **base_rec, "finished_at": utc_now_iso(), "duration_ms": 0, "status": "blocked",
                    "phase": "provider_policy", "flags": 0, "error": redact_error(err),
                })
            raise
        if dry_run:
            return pack, tokens

        started = time.monotonic()
        try:
            text = adapters[model](f"{INSTRUCTION}\n\n{pack}")
        except Blocked as err:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            redacted = redact_error(err)
            append_run_record(home, {
                **base_rec, "finished_at": utc_now_iso(), "duration_ms": elapsed_ms, "status": "blocked",
                "phase": "provider_guard", "flags": 0, "error": redacted,
            })
            raise Blocked(redacted) from None
        except ToolMissing as err:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            redacted = redact_error(err)
            append_run_record(home, {
                **base_rec, "finished_at": utc_now_iso(), "duration_ms": elapsed_ms, "status": "tool_missing",
                "flags": 0, "error": redacted,
            })
            raise ToolMissing(redacted, run_id=rid) from None
        except AskError as err:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            status = _classify_ask_error(err)
            redacted = redact_error(err)
            append_run_record(home, {
                **base_rec, "finished_at": utc_now_iso(), "duration_ms": elapsed_ms, "status": status,
                "flags": 0, "error": redacted,
            })
            raise AskError(redacted, run_id=rid) from None
        except Exception as err:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            redacted = redact_error(err)
            append_run_record(home, {
                **base_rec, "finished_at": utc_now_iso(), "duration_ms": elapsed_ms, "status": "failed",
                "flags": 0, "error": redacted,
            })
            raise AskError(f"{model} failed: {redacted}", run_id=rid) from None
        elapsed_ms = int((time.monotonic() - started) * 1000)

        try:
            check_text(text, "the answer", "Nothing was written to your files.")
        except Blocked as err:
            append_run_record(home, {
                **base_rec, "finished_at": utc_now_iso(), "duration_ms": elapsed_ms, "status": "blocked",
                "phase": "inbound_answer", "flags": 0, "error": redact_error(err),
            })
            raise

        flags = check_answer(text)
        note = model_call_note(len(flags))  # the count only: never the answer or the flag texts
        run_rec = {
            **base_rec, "finished_at": utc_now_iso(), "duration_ms": elapsed_ms,
            "status": "ok", "flags": len(flags),
        }
        record_result(home, path, expected_model, text, day, note, run_id=rid, run_record=run_rec)
        return path


def run_review(home, task_id, reviewers=("codex", "claude"), budget=6000, dry_run=False, adapters=None,
               today=None, diff_text="", repo=None, commit="HEAD", run_id=None):
    """Run an independent blind review (rule 7) across multiple models on the same pre-committed facts-only pack."""
    adapters = adapters or ADAPTERS
    cleaned = [r.strip() for r in reviewers if r and r.strip()]
    if not cleaned:
        raise ValueError("Pass at least one reviewer model.")
    for r in cleaned:
        if r not in adapters:
            raise ValueError(f"Unknown model '{r}'. Choose one of: {', '.join(sorted(adapters))}.")
    repo, req_commit = _normalize_repo_and_commit(repo, commit)

    path = task_file(home, task_id)
    day = today or dt.date.today()
    group_id = validate_run_id(run_id) if run_id is not None else new_run_id(day)
    expected_model = ",".join(f"review:{label(r)}" for r in cleaned)

    with run_lock(home if not dry_run else None, group_id):
        # Check persisted parent BEFORE inspecting the repository so retries replay even if the repo was later deleted
        if not dry_run:
            existing_group = get_run_record(home, group_id, normalize=True)
            if existing_group is not None:
                _verify_review_identity(
                    existing_group, path.stem, expected_model, repo, req_commit, budget=budget, diff_text=diff_text,
                )
                if existing_group.get("status") == "ok":
                    return {
                        "pack": "", "tokens": int(existing_group.get("tokens", 0)),
                        "sha256": existing_group.get("context_sha256", ""), "reviewers": cleaned, "path": path,
                        "group_run_id": group_id, "commit_sha": existing_group.get("commit_sha"), "results": [],
                    }
                raise _reconstruct_persisted_error(home, existing_group)

        diff_sha = _diff_digest(diff_text)
        group_started_iso = utc_now_iso()
        try:
            repo_info = inspect_repo_commit(repo, req_commit) if repo is not None else None
        except Exception as err:
            if not dry_run:
                redacted = redact_error(err)
                append_run_record(home, {
                    "schema_version": RUN_SCHEMA_VERSION, "run_id": group_id, "parent_run_id": None,
                    "date": day.isoformat(), "started_at": group_started_iso, "finished_at": utc_now_iso(),
                    "command": "review_group", "task_id": path.stem, "model": expected_model,
                    "locality": "mixed", "context_sha256": pack_hash(""), "tokens": 0, "budget": budget,
                    "diff_sha256": diff_sha, "duration_ms": 0, "status": "failed", "terminal": True, "flags": 0,
                    "child_run_ids": [], "commit_sha": None, "requested_commit": req_commit,
                    "repo": str(Path(repo).resolve()) if repo is not None else None, "error": redacted,
                })
                raise AskError(redacted) from err
            raise

        pack, tokens = build_review_pack(home, task_id, budget, diff_text=diff_text, repo_info=repo_info)
        digest = pack_hash(pack)
        commit_sha = repo_info["commit_sha"] if repo_info else None
        repo_label = str(repo_info["repo"]) if repo_info else None
        data_tier = task_data_tier(path)

        try:
            check_text(pack, "the review pack", "Nothing was sent.")
        except Blocked as err:
            if not dry_run:
                append_run_record(home, {
                    "schema_version": RUN_SCHEMA_VERSION, "run_id": group_id, "parent_run_id": None,
                    "date": day.isoformat(), "started_at": group_started_iso, "finished_at": utc_now_iso(),
                    "command": "review_group", "task_id": path.stem, "model": expected_model,
                    "locality": "mixed", "context_sha256": digest, "tokens": tokens, "budget": budget,
                    "diff_sha256": diff_sha, "duration_ms": 0, "status": "blocked", "terminal": True,
                    "phase": "outbound_context", "flags": 0, "child_run_ids": [], "commit_sha": commit_sha,
                    "requested_commit": req_commit, "repo": repo_label, "error": redact_error(err),
                })
            raise

        blocked_reviewers = []
        for reviewer in cleaned:
            if reviewer not in PROVIDERS:
                continue
            allowed, reason = check_provider_allowed(data_tier, reviewer, full=False)
            if not allowed:
                blocked_reviewers.append(f"{reviewer}: {reason}")
        if blocked_reviewers:
            err = Blocked("Provider policy blocked review: " + "; ".join(blocked_reviewers))
            if not dry_run:
                append_run_record(home, {
                    "schema_version": RUN_SCHEMA_VERSION, "run_id": group_id, "parent_run_id": None,
                    "date": day.isoformat(), "started_at": group_started_iso, "finished_at": utc_now_iso(),
                    "command": "review_group", "task_id": path.stem, "model": expected_model,
                    "locality": "mixed", "context_sha256": digest, "tokens": tokens, "budget": budget,
                    "data_tier": data_tier, "diff_sha256": diff_sha, "duration_ms": 0, "status": "blocked",
                    "terminal": True, "phase": "provider_policy", "flags": 0, "child_run_ids": [],
                    "commit_sha": commit_sha, "requested_commit": req_commit, "repo": repo_label,
                    "error": redact_error(err),
                })
            raise err

        if dry_run:
            return {
                "pack": pack, "tokens": tokens, "sha256": digest, "reviewers": cleaned, "path": path,
                "commit_sha": commit_sha, "results": [],
            }

        results = []
        child_ids = []
        group_started = time.monotonic()
        first_err = None

        for idx, r in enumerate(cleaned, 1):
            child_id = f"{group_id}-c{idx}" if run_id else new_run_id(day)
            child_ids.append(child_id)
            who = f"review:{label(r)}"
            if run_id:
                existing_child = get_run_record(home, child_id, normalize=True)
                if existing_child is not None:
                    _verify_review_child_identity(
                        existing_child, group_id, path.stem, who, digest, repo_label, commit_sha, req_commit,
                        budget=budget, diff_sha=diff_sha,
                    )
                    if existing_child.get("status") == "ok":
                        flag_count = int(existing_child.get("flags", 0))
                        results.append({
                            "model": r, "label": who, "run_id": child_id,
                            "text": "", "flags": ["persisted_flag"] * flag_count,
                        })
                    elif first_err is None:
                        first_err = _reconstruct_persisted_error(home, existing_child)
                    continue

            locality = PROVIDERS.get(r, {}).get("locality", "remote")
            child_started_iso = utc_now_iso()
            base_child = {
                "schema_version": RUN_SCHEMA_VERSION, "run_id": child_id, "parent_run_id": group_id,
                "date": day.isoformat(), "started_at": child_started_iso, "command": "review",
                "task_id": path.stem, "model": who, "locality": locality, "context_sha256": digest,
                "tokens": tokens, "budget": budget, "diff_sha256": diff_sha, "commit_sha": commit_sha,
                "requested_commit": req_commit, "repo": repo_label, "data_tier": data_tier, "terminal": True,
            }
            started = time.monotonic()
            phase = None
            try:
                try:
                    with _isolated_git_worktree(repo_info):
                        text = adapters[r](f"{REVIEW_INSTRUCTION}\n\n{pack}")
                except Blocked:
                    phase = "provider_guard"
                    raise
                elapsed_ms = int((time.monotonic() - started) * 1000)
                try:
                    check_text(text, f"the review from {r}", "Nothing was written to your files.")
                except Blocked:
                    phase = "inbound_answer"
                    raise
            except (ToolMissing, AskError, Blocked) as err:
                elapsed_ms = int((time.monotonic() - started) * 1000)
                if isinstance(err, ToolMissing):
                    st = "tool_missing"
                elif isinstance(err, Blocked):
                    st = "blocked"
                else:
                    st = _classify_ask_error(err)
                redacted = redact_error(err)
                fail_child = {
                    **base_child, "finished_at": utc_now_iso(), "duration_ms": elapsed_ms, "status": st,
                    "flags": 0, "error": redacted,
                }
                if phase:
                    fail_child["phase"] = phase
                append_run_record(home, fail_child)
                if first_err is None:
                    first_err = type(err)(redacted)
                continue
            except Exception as err:
                elapsed_ms = int((time.monotonic() - started) * 1000)
                redacted = redact_error(err)
                append_run_record(home, {
                    **base_child, "finished_at": utc_now_iso(), "duration_ms": elapsed_ms, "status": "failed",
                    "flags": 0, "error": redacted,
                })
                if first_err is None:
                    first_err = AskError(f"{r} failed: {redacted}")
                continue

            flags = check_answer(text)
            child_rec = {
                **base_child, "finished_at": utc_now_iso(), "duration_ms": elapsed_ms,
                "status": "ok", "flags": len(flags),
            }
            record_result(home, path, who, text, day, model_call_note(len(flags)), run_id=child_id, run_record=child_rec)
            results.append({"model": r, "label": who, "run_id": child_id, "text": text, "flags": flags})

        group_elapsed = int((time.monotonic() - group_started) * 1000)
        if first_err is None:
            group_status = "ok"
        elif results:
            group_status = "partial"
        else:
            group_status = "failed"

        parent_rec = {
            "schema_version": RUN_SCHEMA_VERSION, "run_id": group_id, "parent_run_id": None,
            "date": day.isoformat(), "started_at": group_started_iso, "finished_at": utc_now_iso(),
            "command": "review_group", "task_id": path.stem, "model": expected_model,
            "locality": "mixed", "context_sha256": digest, "tokens": tokens, "budget": budget,
            "data_tier": data_tier, "diff_sha256": diff_sha, "duration_ms": group_elapsed,
            "status": group_status, "terminal": True, "flags": sum(len(r["flags"]) for r in results),
            "child_run_ids": child_ids, "commit_sha": commit_sha,
            "requested_commit": req_commit, "repo": repo_label,
        }
        if first_err is not None:
            parent_rec["error"] = redact_error(first_err)
        append_run_record(home, parent_rec)
        if first_err is not None:
            raise first_err

        return {
            "pack": pack, "tokens": tokens, "sha256": digest, "reviewers": cleaned, "path": path,
            "group_run_id": group_id, "commit_sha": commit_sha, "results": results,
        }
