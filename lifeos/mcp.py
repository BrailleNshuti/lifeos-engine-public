"""lifeos mcp: a local MCP server (JSON-RPC over stdin and stdout, standard library only).

Chat apps that run local MCP servers can then read and write the LifeOS task files without copy and paste.
Everything stays inside the data repo: tasks/ and logs/ledger.csv. Every write goes through the privacy guard.
"""
import json

from . import __version__, ask, delegate
from .context import build_pack, explain_pack, render_explanation, task_file
from .tasks import list_tasks, new_task

STR = {"type": "string"}


def _schema(props, required):
    return {"type": "object", "properties": props, "required": required}


TOOLS = [
    ("lifeos_task_list", "List LifeOS task files with status and due date.",
     _schema({"status": {"type": "string", "enum": ["inbox", "doing", "done"]}}, [])),
    ("lifeos_task_new", "Create a task file from one sentence. The owner writes the done_when line.",
     _schema({"sentence": STR}, ["sentence"])),
    ("lifeos_context", "Read a task with the rules (and, with full=true, now.md and me.md) as a context pack, or explain=true for provenance.",
     _schema({"task": STR, "budget": {"type": "integer"}, "full": {"type": "boolean"}, "explain": {"type": "boolean"}}, ["task"])),
    ("lifeos_result_write", "Append your result to a task file under '## Result'. Class C data is refused.",
     _schema({"task": STR, "model": STR, "text": STR}, ["task", "model", "text"])),
    ("lifeos_ask", "Send a task to another model (codex, claude, gemini, ollama, qwen) and write its answer into the task file.",
     _schema({"task": STR, "model": STR, "budget": {"type": "integer"}, "full": {"type": "boolean"}}, ["task", "model"])),
    ("lifeos_delegate", "Let LifeOS pick the best-fitting model for a task (or pass model to choose), run it, "
     "and return its answer here. The answer is also appended to the task file.",
     _schema({"task": STR, "model": STR, "budget": {"type": "integer"}, "full": {"type": "boolean"}}, ["task"])),
    ("lifeos_review", "Run an independent blind review (rule 7) across multiple models on the task's facts-only pack (and optional git repo/commit).",
     _schema({"task": STR, "reviewers": STR, "repo": STR, "commit": STR, "budget": {"type": "integer"}}, ["task"])),
]

INSTRUCTIONS = ("You are the lead. Work happens in task files. For work that fits another model (code, long reading, "
                "private sorting), call lifeos_delegate with the task id; read the answer it returns, check it against "
                "rules.md (proof, sources, how it could be wrong), then say plainly if the CHECK line flags anything or you see nonsense, and write your decision or next step with "
                "lifeos_result_write. For blind multi-model verification (rule 7), call lifeos_review. Never delegate class C data (IDs, bank, passwords, health, tenant data). "
                "Private files such as a bank CSV never go into this chat or to any cloud model: tell the owner to run "
                "`lifeos sort-csv <file>` in PowerShell (local, offline). "
                "The owner makes the final call; sending, buying, deleting and publishing need his yes.")


def _run_tool(home, name, a):
    if name == "lifeos_task_list":
        rows = list_tasks(home, a.get("status"))
        return "\n".join(f"{t['id']}  {t['status']}  {t['due']}  {t['goal']}" for t in rows) or "No tasks."
    if name == "lifeos_task_new":
        ask.check_text(a["sentence"], "the task sentence", "No task file was created.")
        return str(new_task(home, a["sentence"]).relative_to(home))
    if name == "lifeos_context":
        task_file(home, a["task"])  # a missing, empty or unsafe id is an error, never a pack without the task
        names = None if a.get("full") else ask.MINIMAL
        if a.get("explain"):
            return render_explanation(explain_pack(home, a["task"], a.get("budget", 6000), task_first=True, names=names))
        return build_pack(home, a["task"], a.get("budget", 6000), task_first=True, names=names)[0]
    if name == "lifeos_result_write":
        return f"written to {ask.write_result(home, a['task'], a['model'], a['text']).relative_to(home)}"
    if name == "lifeos_delegate":
        out = delegate.run_delegate(home, a["task"], a.get("model"), a.get("budget", 6000), full=bool(a.get("full")))
        warn = f"\n\nCHECK (free, no model): {'; '.join(out['flags'])}" if out["flags"] else ""
        return f"{out['model']} answered ({out['reason']}).\n\n{out['text']}{warn}"
    if name == "lifeos_ask":
        path = ask.run_ask(home, a["model"], a["task"], a.get("budget", 6000), full=bool(a.get("full")))
        return f"{a['model']} answered; result appended to {path.relative_to(home)}"
    if name == "lifeos_review":
        revs = [r.strip() for r in (a.get("reviewers") or "codex,claude").split(",") if r.strip()]
        out = ask.run_review(
            home, a["task"], reviewers=revs, budget=a.get("budget", 6000),
            repo=a.get("repo"), commit=a.get("commit", "HEAD") if "commit" in a else "HEAD",
        )
        parts = [f"Blind review ({out['group_run_id']}, pack {out['sha256']}) appended to {out['path'].relative_to(home)}:"]
        for r in out["results"]:
            parts.append(f"\n--- {r['label']} ({r['run_id']}) ---\n{r['text']}")
        return "\n".join(parts)
    raise KeyError(name)


def _reply(id, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": id}
    msg["error" if error else "result"] = error or result
    return msg


def handle(home, msg):
    """Return the JSON-RPC reply for one message, or None for notifications."""
    if not isinstance(msg, dict):
        return _reply(None, error={"code": -32600, "message": "Invalid Request: a JSON object is expected"})
    id, method, params = msg.get("id"), msg.get("method", ""), msg.get("params") or {}
    if not isinstance(params, dict):
        return _reply(id, error={"code": -32602, "message": "Invalid params: an object is expected"})
    if id is None:
        return None
    if method == "initialize":
        return _reply(id, {"protocolVersion": params.get("protocolVersion", "2025-03-26"),
                           "capabilities": {"tools": {}},
                           "serverInfo": {"name": "lifeos", "version": __version__},
                           "instructions": INSTRUCTIONS})
    if method == "ping":
        return _reply(id, {})
    if method == "tools/list":
        return _reply(id, {"tools": [{"name": n, "description": d, "inputSchema": s} for n, d, s in TOOLS]})
    if method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str) or name not in {t[0] for t in TOOLS}:
            return _reply(id, error={"code": -32602, "message": f"Unknown tool {name}"})
        try:
            text, bad = _run_tool(home, name, params.get("arguments") or {}), False
        except (ask.Blocked, ask.AskError, FileNotFoundError, ValueError, KeyError) as error:
            raw = str(error.args[0] if isinstance(error, KeyError) else error)
            text, bad = ask.redact_error(raw), True
        except Exception as error:  # a tool must never take the whole server down
            text, bad = ask.redact_error(f"{type(error).__name__}: {error}"), True
        return _reply(id, {"content": [{"type": "text", "text": text}], "isError": bad})
    return _reply(id, error={"code": -32601, "message": f"Method not found: {method}"})


def serve(home, stdin, stdout):
    for line in stdin:
        if not line.strip():
            continue
        try:
            reply = handle(home, json.loads(line))
        except json.JSONDecodeError:
            reply = _reply(None, error={"code": -32700, "message": "Parse error"})
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()
