"""6-question model router with 5-tier data policy and token/call budget guard.

The model choice is the same seat table `delegate` runs (`seats.choose`).
"""
import datetime as dt
import re

from . import seats
from .context import task_file
from .policy import check_provider_allowed, classify_path, normalize_tier, provider_locality
from .store import read_run_records

WEEKLY_TOKEN_BUDGET = seats.WEEKLY_TOKENS  # one ruler: seats.py owns the cloud budget
WEEKLY_CALL_BUDGET = seats.WEEKLY_CALLS


def _extract_meta_and_text(path):
    raw = path.read_text(encoding="utf-8")
    goal_m = re.search(r"^goal:\s*(.+)$", raw, re.M)
    level_m = re.search(r"^level:\s*(L[0-3])\b", raw, re.M)
    body = raw.split("## Result", 1)[0].split("---", 2)[-1]
    goal = goal_m.group(1).strip() if goal_m else path.stem
    level = level_m.group(1).strip() if level_m else None
    return goal, level, f"{goal}\n{body}"


def _pick_task_route(text, explicit_level=None):
    primary, reviewer, default_lvl, reason = seats.kind(text)
    return primary, reviewer, explicit_level or default_lvl, reason


def evaluate_route(home, task_or_text, tier=None, full=False, token_budget=WEEKLY_TOKEN_BUDGET):
    """Evaluate all 6 routing questions for a task ID or free-text description."""
    is_task_file = False
    rel_path = ""
    explicit_level = None
    try:
        tpath = task_file(home, task_or_text)
        is_task_file = True
        rel_path = tpath.relative_to(home).as_posix()
        goal, explicit_level, text = _extract_meta_and_text(tpath)
    except Exception:
        goal = str(task_or_text or "").strip()
        text = goal

    # Question 1: Is it confidential work data?
    work_leak = bool(re.search(r"\b(work\s+client|confidential\s+work|internal\s+deal|client\s+dataset)\b", text, re.I))
    q1 = {
        "question": "1. Is it confidential work data (Rule 9)?",
        "verdict": "BLOCK_WORK_LANE" if work_leak else "PASS",
        "detail": (
            "Confidential work data must stay in the employer's own approved tools; use Prompt Lab with synthetic data only."
            if work_leak else "Personal/study/lab or synthetic Prompt Lab scope."
        ),
    }

    # Question 2: Can a Tier-0 script or CLI command do it?
    tier0_match = re.search(r"\b(weekly\s+numbers|scoreboard\s+math|sort\s+bank\s+csv|validate\s+prompt\s+card)\b", text, re.I)
    q2 = {
        "question": "2. Can a Tier-0 script or CLI command do it without AI?",
        "verdict": "TIER_0_SCRIPT" if tier0_match else "NEEDS_MODEL",
        "detail": (
            "Use deterministic CLI (`lifeos week`, `lifeos log`, `lifeos sort-csv`, or `lifeos lab score`)."
            if tier0_match else "Requires model reasoning or generation."
        ),
    }

    # Question 3: Data classification tier (5-tier policy)
    effective_tier = normalize_tier(tier) if tier else (classify_path(rel_path) if rel_path else "PERSONAL")
    if re.search(r"\b(iban|bank\s+csv|health\.csv|medical|residence\s+permit\s+number)\b", text, re.I):
        effective_tier = "SENSITIVE"

    # Question 4 & 5: Task type matrix and risk/autonomy level
    primary, reviewer, level, reason = _pick_task_route(text, explicit_level=explicit_level)
    if effective_tier == "SENSITIVE":
        primary, reviewer, reason = "qwen", "none", "SENSITIVE data forced to local qwen"

    allowed, policy_reason = check_provider_allowed(effective_tier, primary, full=full)
    q3 = {
        "question": "3. Data classification & provider locality (5-tier policy)?",
        "tier": effective_tier,
        "allowed": allowed,
        "detail": policy_reason,
    }
    q4 = {
        "question": "4. Which model fits the task best?",
        "primary": primary,
        "locality": provider_locality(primary),
        "reason": reason,
    }
    blind_review_required = level in ("L2", "L3") and reviewer != "none" and provider_locality(primary) == "remote"
    q5 = {
        "question": "5. What if the answer is wrong (Autonomy & Rule 7 blind review)?",
        "level": level,
        "reviewer": reviewer,
        "blind_review_required": blind_review_required,
        "owner_approval_required": level == "L3",
    }

    # Question 6: per-seat share, usage-limit rest, and the replacement chain
    records = read_run_records(home)
    now = dt.datetime.now(dt.timezone.utc)
    plan = seats.budget(records, now)
    used_tokens = plan["used_tokens"]
    used_calls = plan["used_calls"]
    resting = seats.pressure(records, now)
    seat_tier = "SENSITIVE" if effective_tier == "SENSITIVE" else effective_tier
    selected_model, seat_reason, fallbacks = seats.choose(text, seat_tier, resting)
    if selected_model != primary and selected_model in seats.CHAINS:
        primary = selected_model
        if primary in ("qwen", "ollama"):
            reviewer = "none"
        blind_review_required = (
            level in ("L2", "L3") and reviewer != "none" and provider_locality(primary) == "remote"
        )
        q4["primary"] = primary
        q4["locality"] = provider_locality(primary)
        q4["reason"] = seat_reason
        q5["reviewer"] = reviewer
        q5["blind_review_required"] = blind_review_required
    q6 = {
        "question": "6. Budget & fallback status?",
        "used_tokens": used_tokens,
        "token_budget": plan["cap_tokens"],
        "used_calls": used_calls,
        "call_budget": WEEKLY_CALL_BUDGET,
        "fallback_active": bool(resting),
        "fallbacks": fallbacks,
        "skipped": resting,
        "selected_model": selected_model,
    }

    blocked = work_leak or not allowed
    return {
        "target": rel_path if is_task_file else goal[:80],
        "goal": goal,
        "blocked": blocked,
        "selected_model": None if blocked else ("tier0-cli" if tier0_match else selected_model),
        "reviewer": reviewer if not blocked else None,
        "level": level,
        "tier": effective_tier,
        "blind_review_required": blind_review_required and not blocked,
        "questions": [q1, q2, q3, q4, q5, q6],
    }


def render_route(decision):
    """Render a concise human-readable 6-question routing decision."""
    status = "BLOCKED" if decision["blocked"] else f"ROUTE -> {decision['selected_model']}"
    rev = f" (blind review: {decision['reviewer']})" if decision.get("blind_review_required") else ""
    lines = [
        f"Route Decision [{status}{rev}] · level {decision['level']} · tier {decision['tier']}",
        f"Target: {decision['target']} — {decision['goal']}",
        "",
    ]
    for q in decision["questions"]:
        head = q["question"]
        detail = q.get("detail") or q.get("reason") or (
            f"level={q.get('level')}, reviewer={q.get('reviewer')}, owner_yes={q.get('owner_approval_required')}"
            if "blind_review_required" in q
            else f"tokens={q.get('used_tokens')}/{q.get('token_budget')}, calls={q.get('used_calls')}/{q.get('call_budget')}, fallbacks={q.get('fallbacks')}"
        )
        lines.append(f"  {head}\n    -> {detail}")
    return "\n".join(lines)
