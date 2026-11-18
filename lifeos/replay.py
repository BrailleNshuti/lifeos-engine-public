"""Replay a recorded `ask` run: rebuild the context pack from today's files and compare it with what was sent.

New run records store a SHA-256 per context file (never the content) and the length of the task file at that moment.
Answers are appended to the task file, so the rebuild cuts the task back to that length first. Same hash = the model
saw exactly this input. A different hash names the file that changed (`git log -- <file>` then shows when).
"""
from . import ask
from .context import explain_pack, pack_hash
from .store import get_run_record


class ReplayError(Exception):
    pass


def replay_run(home, run_id):
    rec = get_run_record(home, run_id, normalize=False)
    if rec is None:
        raise ReplayError(f"Run {run_id} not found in logs/runs.jsonl.")
    out = {"run_id": run_id, "command": rec.get("command"), "supported": False, "identical": None,
           "recorded_sha256": rec.get("context_sha256"), "current_sha256": None, "files": [], "changed": [], "reason": ""}
    if rec.get("command") != "ask":
        out["reason"] = f"only ask runs can be replayed (this one is '{rec.get('command')}')"
        return out
    if "context_files" not in rec or "task_chars" not in rec:
        out["reason"] = "this run was recorded before replay support; it has no per-file digests"
        return out
    full = bool(rec.get("full"))
    info = explain_pack(home, rec["task_id"], rec["budget"], task_first=True,
                        names=None if full else ask.MINIMAL, task_limit=rec["task_chars"])
    now = {i["name"]: i["sha256"] for i in info["items"] if i["status"] in ("included", "trimmed")}
    then = {f["name"]: f["sha256"] for f in rec["context_files"]}
    out["supported"] = True
    out["current_sha256"] = info["sha256"]
    out["files"] = [{"name": n, "recorded": then.get(n), "current": now.get(n), "same": then.get(n) == now.get(n)}
                    for n in sorted(set(then) | set(now))]
    out["changed"] = [f["name"] for f in out["files"] if not f["same"]]
    out["identical"] = info["sha256"] == rec.get("context_sha256") and not out["changed"]
    return out


def render(out):
    head = f"Run {out['run_id']} ({out['command']})"
    if not out["supported"]:
        return f"{head}: cannot replay: {out['reason']}."
    if out["identical"]:
        return f"{head}: identical. The model saw exactly this input.\nsha256 {out['current_sha256']}"
    lines = [f"{head}: DIFFERENT. Files that changed since the run:"]
    lines += [f"  {n}" for n in out["changed"]] or ["  (the pack differs but every listed file matches: budget or file set changed)"]
    return "\n".join(lines)
