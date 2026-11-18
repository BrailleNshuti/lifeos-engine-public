"""Execution analytics and audit trail inspector for logs/runs.jsonl."""
from .store import TERMINAL_RUN_STATUSES, read_run_records


def filter_runs(home, status=None, model=None, task=None, limit=20):
    """Return normalized run records matching optional status, model, and task prefix filters (newest first)."""
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        raise ValueError("limit must be a positive integer.")
    if status is not None and status not in TERMINAL_RUN_STATUSES:
        raise ValueError(f"Unknown status '{status}'. Allowed: {', '.join(TERMINAL_RUN_STATUSES)}.")

    records = read_run_records(home, normalize=True)
    matched = []
    model_norm = model.strip().lower() if model else None
    task_norm = task.strip() if task else None

    for rec in records:
        if status and rec.get("status") != status:
            continue
        if model_norm:
            rec_model = str(rec.get("model") or "").lower()
            reviewers = [str(r).lower() for r in (rec.get("reviewers") or [])]
            if rec_model != model_norm and model_norm not in reviewers:
                continue
        if task_norm:
            rec_task = str(rec.get("task") or "")
            if not rec_task.startswith(task_norm):
                continue
        matched.append(rec)

    matched.reverse()
    return matched[:limit] if limit else matched


def summarize_runs(home, status=None, model=None, task=None, limit=20):
    """Return a structured summary and recent filtered run records from logs/runs.jsonl."""
    all_matched = filter_runs(home, status=status, model=model, task=task, limit=None)
    by_status = {}
    by_model = {}
    by_command = {}
    durations = []
    tokens_total = 0

    for rec in all_matched:
        st = rec.get("status") or "unknown"
        by_status[st] = by_status.get(st, 0) + 1
        cmd = rec.get("command") or "unknown"
        by_command[cmd] = by_command.get(cmd, 0) + 1
        mdl = rec.get("model")
        if mdl:
            by_model[mdl] = by_model.get(mdl, 0) + 1
        dur = rec.get("duration_s")
        if isinstance(dur, (int, float)) and not isinstance(dur, bool):
            durations.append(float(dur))
        tok = rec.get("context_tokens")
        if isinstance(tok, int) and not isinstance(tok, bool):
            tokens_total += tok

    recent = all_matched[:limit] if limit else all_matched
    return {
        "total_matching": len(all_matched),
        "shown": len(recent),
        "by_status": dict(sorted(by_status.items())),
        "by_model": dict(sorted(by_model.items(), key=lambda kv: (-kv[1], kv[0]))),
        "by_command": dict(sorted(by_command.items())),
        "avg_duration_s": round(sum(durations) / len(durations), 2) if durations else None,
        "total_context_tokens": tokens_total,
        "runs": recent,
    }


def render_runs(summary):
    """Render a concise human-readable audit table from summarize_runs()."""
    if not summary["total_matching"]:
        return "Runs: 0 matching records in logs/runs.jsonl"
    status_str = ", ".join(f"{k} {v}" for k, v in summary["by_status"].items())
    model_str = ", ".join(f"{k} {v}" for k, v in summary["by_model"].items()) or "none"
    avg_str = f"{summary['avg_duration_s']}s" if summary["avg_duration_s"] is not None else "n/a"
    lines = [
        f"Runs: {summary['total_matching']} total (showing {summary['shown']}) | statuses: {status_str}",
        f"Models: {model_str} | avg duration: {avg_str} | context tokens: {summary['total_context_tokens']}",
        "",
    ]
    for rec in summary["runs"]:
        rid = str(rec.get("run_id") or "?")
        cmd = str(rec.get("command") or "?")
        st = str(rec.get("status") or "?")
        mdl = rec.get("model") or ",".join(rec.get("reviewers") or []) or "-"
        tsk = rec.get("task") or "-"
        dur = f"{rec['duration_s']}s" if isinstance(rec.get("duration_s"), (int, float)) else "-"
        lines.append(f"  {rid:<20} {st:<12} {cmd:<12} {mdl:<14} {dur:<8} {tsk}")
    return "\n".join(lines)
