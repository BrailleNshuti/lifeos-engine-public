"""lifeos mcp: a local MCP server (JSON-RPC over stdin and stdout, standard library only).

Chat apps that run local MCP servers can then read and write the LifeOS task files without copy and paste.
Everything stays inside the data repo: tasks/ and logs/ledger.csv. Every write goes through the privacy guard.
"""
import json

from . import __version__, ask
from .context import _task_file, build_pack
from .tasks import list_tasks, new_task

STR = {"type": "string"}


def _schema(props, required):
    return {"type": "object", "properties": props, "required": required}


TOOLS = [
    ("lifeos_task_list", "List LifeOS task files with status and due date.",
     _schema({"status": {"type": "string", "enum": ["inbox", "doing", "done"]}}, [])),
    ("lifeos_task_new", "Create a task file from one sentence. The owner writes the done_when line.",
     _schema({"sentence": STR}, ["sentence"])),
    ("lifeos_context", "Read a task with the rules (and, with full=true, now.md and me.md) as a context pack.",
     _schema({"task": STR, "budget": {"type": "integer"}, "full": {"type": "boolean"}}, ["task"])),
    ("lifeos_result_write", "Append your result to a task file under '## Result'. Class C data is refused.",
     _schema({"task": STR, "model": STR, "text": STR}, ["task", "model", "text"])),
    ("lifeos_ask", "Send a task to another model (codex, claude, gemini, ollama) and write its answer into the task file.",
     _schema({"task": STR, "model": STR, "budget": {"type": "integer"}, "full": {"type": "boolean"}}, ["task", "model"])),
]


def _run_tool(home, name, a):
    if name == "lifeos_task_list":
        rows = list_tasks(home, a.get("status"))
        return "\n".join(f"{t['id']}  {t['status']}  {t['due']}  {t['goal']}" for t in rows) or "No tasks."
    if name == "lifeos_task_new":
        return str(new_task(home, a["sentence"]).relative_to(home))
    if name == "lifeos_context":
        _task_file(home, a["task"])  # a missing, empty or unsafe id is an error, never a pack without the task
        return build_pack(home, a["task"], a.get("budget", 6000), task_first=True,
                          names=None if a.get("full") else ask.MINIMAL)[0]
    if name == "lifeos_result_write":
        return f"written to {ask.write_result(home, a['task'], a['model'], a['text']).relative_to(home)}"
    if name == "lifeos_ask":
        path = ask.run_ask(home, a["model"], a["task"], a.get("budget", 6000), full=bool(a.get("full")))
        return f"{a['model']} answered; result appended to {path.relative_to(home)}"
    raise KeyError(name)


def _reply(id, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": id}
    msg["error" if error else "result"] = error or result
    return msg


def handle(home, msg):
    """Return the JSON-RPC reply for one message, or None for notifications."""
    id, method, params = msg.get("id"), msg.get("method", ""), msg.get("params") or {}
    if id is None:
        return None
    if method == "initialize":
        return _reply(id, {"protocolVersion": params.get("protocolVersion", "2025-03-26"),
                           "capabilities": {"tools": {}},
                           "serverInfo": {"name": "lifeos", "version": __version__}})
    if method == "ping":
        return _reply(id, {})
    if method == "tools/list":
        return _reply(id, {"tools": [{"name": n, "description": d, "inputSchema": s} for n, d, s in TOOLS]})
    if method == "tools/call":
        name = params.get("name")
        if name not in {t[0] for t in TOOLS}:
            return _reply(id, error={"code": -32602, "message": f"Unknown tool {name}"})
        try:
            text, bad = _run_tool(home, name, params.get("arguments") or {}), False
        except (ask.Blocked, ask.AskError, FileNotFoundError, ValueError, KeyError) as error:
            text, bad = str(error.args[0] if isinstance(error, KeyError) else error), True
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
