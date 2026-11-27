"""lifeos mcp: a local MCP server (JSON-RPC over stdin and stdout, standard library only).

Chat apps that run local MCP servers can then read and write the LifeOS task files without copy and paste.
Everything stays inside the data repo: tasks/ and logs/ledger.csv. Every write goes through the privacy guard.
"""
import json

from . import __version__, ask, bakeoff, cockpit, delegate, exam, kaizen, log, router, runs, selfcheck, showcase, waiting
from .context import build_pack, explain_pack, render_explanation, task_file
from .store import new_run_id, validate_run_id
from .tasks import list_tasks, new_task
from .week import build_redteam_pack, draft_weekly_review, render_markdown, week_numbers

STR = {"type": "string"}


def _schema(props, required):
    return {"type": "object", "properties": props, "required": required}


TOOLS = [
    ("lifeos_task_list", "List LifeOS task files with status and due date.",
     _schema({"status": {"type": "string", "enum": ["inbox", "doing", "done"]}}, [])),
    ("lifeos_selfcheck", "Check the owner's own files (ledger chain, task files, ratings log, waiting list). Reads only; names each problem, never repairs.",
     _schema({}, [])),
    ("lifeos_waiting_list", "List what is waiting on the owner or on Claude (waiting.json), numbered. Reads only.",
     _schema({}, [])),
    ("lifeos_task_new", "Create a task file from one sentence. The owner writes the done_when line.",
     _schema({"sentence": STR}, ["sentence"])),
    ("lifeos_context", "Read a task with the rules (and, with full=true, now.md and me.md) as a context pack, or explain=true for provenance.",
     _schema({"task": STR, "budget": {"type": "integer"}, "full": {"type": "boolean"}, "explain": {"type": "boolean"}}, ["task"])),
    ("lifeos_result_write", "Append your result to a task file under '## Result'. Class C data is refused.",
     _schema({"task": STR, "model": STR, "text": STR}, ["task", "model", "text"])),
    ("lifeos_ask", "Send a task to another model (codex, claude, gemini, ollama, qwen) and write its answer into the task file. Pass run_id for idempotent retries.",
     _schema({"task": STR, "model": STR, "budget": {"type": "integer"}, "full": {"type": "boolean"}, "run_id": STR}, ["task", "model"])),
    ("lifeos_delegate", "Pick the best open seat for a task, replace it if that call fails, record why under ## Route, and return the answer. The answer is also appended to the task file.",
     _schema({"task": STR, "model": STR, "budget": {"type": "integer"}, "full": {"type": "boolean"}}, ["task"])),
    ("lifeos_review", "Run an independent blind review (rule 7) across multiple models on the task's facts-only pack (and optional git repo/commit). Pass run_id for idempotent retries.",
     _schema({"task": STR, "reviewers": STR, "repo": STR, "commit": STR, "budget": {"type": "integer"}, "run_id": STR}, ["task"])),
    ("lifeos_week", "Read weekly scoreboard numbers from the logs, draft reviews/<week>.md (draft=true), or generate the facts-only Red-Team pack (redteam=true).",
     _schema({"week": STR, "draft": {"type": "boolean"}, "redteam": {"type": "boolean"}}, [])),
    ("lifeos_log", "Append a validated, guard-checked row to proofs.csv, ledger.csv, health.csv, or hours.csv.",
     _schema({
         "action": {"type": "string", "enum": ["proof", "ledger", "health", "hours"]},
         "area": STR, "proof": STR, "link": STR, "task": STR, "model": STR,
         "minutes": {"type": "number"}, "sleep": {"type": "number"}, "gym": STR,
         "energy": {"type": "integer"}, "hours": {"type": "number"}, "note": STR, "date": STR,
     }, ["action"])),
    ("lifeos_runs", "Inspect execution audit records and summary counts from logs/runs.jsonl.",
     _schema({"status": STR, "model": STR, "task": STR, "limit": {"type": "integer"}}, [])),
    ("lifeos_kaizen", "Run the monthly System Health check and optionally draft reviews/<YYYY-MM>.md.",
     _schema({"month": STR, "draft": {"type": "boolean"}}, [])),
    ("lifeos_route", "Evaluate the 6-question routing decision (confidential-work-data check, Tier-0 check, 5-tier data policy, model pick, L0-L3 blind review, budget guard).",
     _schema({"target": STR, "tier": STR, "full": {"type": "boolean"}}, ["target"])),
    ("lifeos_cockpit", "Export the self-contained visual Braille × LifeOS Cockpit HTML file (<home>/cockpit/index.html).",
     _schema({"export": STR}, [])),
    ("lifeos_exam", "Generate a 60-90 min Monthly No-AI Exam or record a graded exam score into logs/skills.md.",
     _schema({"month": STR, "module": STR, "draft": {"type": "boolean"}, "score_skill": STR, "score_pct": {"type": "integer"}}, [])),
    ("lifeos_bakeoff", "Generate or score a blind Role Bake-Off scorecard with SHA-256 X/Y anonymization.",
     _schema({"quarter": STR, "task_type": STR, "model_a": STR, "model_b": STR, "scores": STR, "draft": {"type": "boolean"}}, [])),
    ("lifeos_showcase", "Generate a Build-in-Public weekly proof post and monthly case study outline.",
     _schema({"week": STR, "draft": {"type": "boolean"}}, [])),
]

INSTRUCTIONS = ("You are the lead. Work happens in task files. For work that fits another model (code, long reading, "
                "private sorting), call lifeos_delegate with the task id; read the answer it returns, check it against "
                "rules.md (proof, sources, how it could be wrong), then say plainly if the CHECK line flags anything or you see nonsense, and write your decision or next step with "
                "lifeos_result_write. For blind multi-model verification (rule 7), call lifeos_review. For reliable retries of lifeos_ask or lifeos_review across lost responses, generate and retain a run_id before the first call and reuse that run_id on retry. Never delegate class C data (IDs, bank, passwords, health, tenant data). "
                "Private files such as a bank CSV never go into this chat or to any cloud model: tell the owner to run "
                "`lifeos sort-csv <file>` in PowerShell (local, offline). "
                "The owner makes the final call; sending, buying, deleting and publishing need his yes.")


def _run_tool(home, name, a):
    if name == "lifeos_task_list":
        rows = list_tasks(home, a.get("status"))
        return "\n".join(f"{t['id']}  {t['status']}  {t['due']}  {t['goal']}" for t in rows) or "No tasks."
    if name == "lifeos_selfcheck":
        return selfcheck.render(selfcheck.run(home))
    if name == "lifeos_waiting_list":
        return waiting.render(waiting.read(home))
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
        said = "".join(f"\n\nNOTE {note}" for note in out.get("notes") or [])
        return f"{out['model']} answered ({out['reason']}).\n\n{out['text']}{said}{warn}"
    if name == "lifeos_ask":
        rid = validate_run_id(a["run_id"]) if a.get("run_id") is not None else new_run_id()
        path = ask.run_ask(
            home, a["model"], a["task"], a.get("budget", 6000), full=bool(a.get("full")), run_id=rid,
        )
        return f"{a['model']} answered ({rid}); result appended to {path.relative_to(home)}"
    if name == "lifeos_review":
        rid = validate_run_id(a["run_id"]) if a.get("run_id") is not None else None
        revs = [r.strip() for r in (a.get("reviewers") or "codex,claude").split(",") if r.strip()]
        out = ask.run_review(
            home, a["task"], reviewers=revs, budget=a.get("budget", 6000),
            repo=a.get("repo"), commit=a.get("commit", "HEAD") if "commit" in a else "HEAD",
            run_id=rid,
        )
        failed = ", ".join(f"{r['model']} {r['summary']}" for r in out.get("failures", []))
        summary = f"{len(revs)} asked, {len(out['results'])} answered" + (f", {failed}" if failed else "")
        parts = [f"Blind review ({out['group_run_id']}, pack {out['sha256']}) appended to {out['path'].relative_to(home)}:",
                 f"Summary: {summary}"]
        for r in out["results"]:
            parts.append(f"\n--- {r['label']} ({r['run_id']}) ---\n{r['text']}")
        return "\n".join(parts)
    if name == "lifeos_week":
        wk = a.get("week")
        if a.get("draft"):
            return f"drafted {draft_weekly_review(home, wk).relative_to(home)}"
        if a.get("redteam"):
            return build_redteam_pack(home, wk)
        return render_markdown(week_numbers(home, wk))
    if name == "lifeos_log":
        act = a.get("action")
        dt_val = a.get("date")
        if act == "proof":
            return log.log_proof(home, a.get("area", ""), a.get("proof", ""), a.get("link", ""), date=dt_val)
        if act == "ledger":
            return log.log_ledger(home, a.get("task", ""), a.get("model", ""), a.get("minutes", ""), a.get("note", ""), date=dt_val)
        if act == "health":
            return log.log_health(home, a.get("sleep", ""), a.get("gym", ""), a.get("energy", ""), note=a.get("note", ""), date=dt_val)
        if act == "hours":
            return log.log_hours(home, a.get("area", ""), a.get("hours", ""), note=a.get("note", ""), date=dt_val)
        raise ValueError(f"Unknown log action '{act}'.")
    if name == "lifeos_runs":
        return runs.render_runs(runs.summarize_runs(
            home, status=a.get("status"), model=a.get("model"), task=a.get("task"), limit=a.get("limit", 20),
        ))
    if name == "lifeos_kaizen":
        if a.get("draft"):
            return f"drafted {kaizen.draft_system_health(home, month=a.get('month')).relative_to(home)}"
        return kaizen.render_system_health(kaizen.system_health(home, month=a.get("month")))
    if name == "lifeos_route":
        return router.render_route(router.evaluate_route(home, a["target"], tier=a.get("tier"), full=bool(a.get("full"))))
    if name == "lifeos_cockpit":
        out = cockpit.export_cockpit(home, out_path=a.get("export"))
        try:
            return f"exported {out.relative_to(home)}"
        except ValueError:
            return f"exported {out}"
    if name == "lifeos_exam":
        if a.get("score_skill"):
            res = exam.record_exam_score(home, a["score_skill"], a.get("score_pct", 0))
            return json.dumps(res)
        if a.get("draft"):
            out = exam.write_exam_draft(home, month=a.get("month"), module=a.get("module") or "Core module", overwrite=True)
            return f"drafted {out.relative_to(home)}"
        return exam.generate_monthly_exam(home, month=a.get("month"), module=a.get("module") or "Core module")
    if name == "lifeos_bakeoff":
        if a.get("draft"):
            out = bakeoff.write_bakeoff(
                home, quarter=a.get("quarter"), task_type=a.get("task_type") or "Decision Memo",
                model_a=a.get("model_a") or "claude", model_b=a.get("model_b") or "chatgpt",
                scores_json=a.get("scores"), overwrite=True,
            )
            return f"drafted {out.relative_to(home)}"
        scores = json.loads(a["scores"]) if a.get("scores") else None
        return bakeoff.render_bakeoff_card(
            a.get("quarter") or "2026-Q4", a.get("task_type") or "Decision Memo",
            model_a=a.get("model_a") or "claude", model_b=a.get("model_b") or "chatgpt", scores=scores,
        )
    if name == "lifeos_showcase":
        if a.get("draft"):
            out = showcase.write_weekly_post(home, week=a.get("week"), overwrite=True)
            return f"drafted {out.relative_to(home)}"
        return showcase.generate_weekly_post(home, week=a.get("week"))
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
