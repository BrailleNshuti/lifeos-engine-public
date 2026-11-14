"""6-Question Section 8.2 Model Router with 5-tier data policy and token/call budget guard."""
import re

from .context import task_file
from .policy import check_provider_allowed, classify_path, normalize_tier, provider_locality
from .runs import summarize_runs

WEEKLY_TOKEN_BUDGET = 120_000
WEEKLY_CALL_BUDGET = 80

TASK_ROUTES = [
    ("qwen", "none", "L1", "private or local CSV/sorting task stays on laptop (qwen)",
     r"private|local(ly)?|csv|sort|classify|categori[sz]e|rename|tidy|offline"),
    ("gemini", "claude", "L1", "long reading, bulk PDFs or live facts go to gemini, synthesized by claude",
     r"price|news|latest|today|job posting|long|pdf|paper|research|summari[sz]e|bulk|read all"),
    ("codex", "claude", "L0", "testing, review, German, quizzes and exam prep go to codex",
     r"bug|test|pytest|review|adversarial|ship|merge|command|german|exam|quiz|learn|teach|vocabulary"),
    ("claude", "codex", "L2", "code architecture/implementation written by claude, checked by codex (D23)",
     r"code|implement|refactor|script|python|function|module|cli|\.py\b|\.js\b|\.ts\b"),
    ("claude", "codex", "L3", "plans, Decision Memos and high-stakes writing drafted by claude with blind check",
     r"plan|write|draft|decide|decision|memo|strategy|email|permit|contract|buy|subscription"),
]
FALLBACK_CHAIN = {
    "qwen": ["ollama"],
    "ollama": [],
    "claude": ["codex", "gemini"],
    "codex": ["claude"],
    "gemini": ["claude", "codex"],
}


def _extract_meta_and_text(path):
    raw = path.read_text(encoding="utf-8")
    goal_m = re.search(r"^goal:\s*(.+)$", raw, re.M)
    level_m = re.search(r"^level:\s*(L[0-3])\b", raw, re.M)
    body = raw.split("## Result", 1)[0].split("---", 2)[-1]
    goal = goal_m.group(1).strip() if goal_m else path.stem
    level = level_m.group(1).strip() if level_m else None
    return goal, level, f"{goal}\n{body}"


def _pick_task_route(text, explicit_level=None):
    for primary, reviewer, default_lvl, reason, pattern in TASK_ROUTES:
        if re.search(rf"(?<![a-z])({pattern})", text, re.I):
            lvl = explicit_level or default_lvl
            return primary, reviewer, lvl, reason
    return "claude", "codex", explicit_level or "L2", "general task routed to claude lead with codex review"


def evaluate_route(home, task_or_text, tier=None, full=False, token_budget=WEEKLY_TOKEN_BUDGET):
    """Evaluate all 6 questions of Master Plan Section 8.2 for a task ID or free-text description."""
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

    # Question 1: Is it confidential employer work data?
    work_leak = bool(re.search(r"\b(employer\s+client|confidential\s+work|internal\s+deal|client\s+dataset)\b", text, re.I))
    q1 = {
        "question": "1. Is it confidential work data (Rule 9 / rule 9)?",
        "verdict": "BLOCK_WORK_LANE" if work_leak else "PASS",
        "detail": (
            "Confidential work data must stay in employer's Console; use Prompt Lab with synthetic data only."
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
        primary, reviewer, reason = "qwen", "none", "SENSITIVE data forced to local qwen (D22)"

    allowed, policy_reason = check_provider_allowed(effective_tier, primary, full=full)
    q3 = {
        "question": "3. Data classification & provider locality (5-tier policy)?",
        "tier": effective_tier,
        "allowed": allowed,
        "detail": policy_reason,
    }
    q4 = {
        "question": "4. Which model fits the task best (Section 8.3 matrix)?",
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

    # Question 6: Budget & fallback chain
    run_stats = summarize_runs(home, limit=100)
    used_tokens = run_stats["total_context_tokens"]
    used_calls = run_stats["total_matching"]
    over_budget = used_tokens > token_budget or used_calls > WEEKLY_CALL_BUDGET
    fallbacks = FALLBACK_CHAIN.get(primary, [])
    selected_model = (fallbacks[0] if (over_budget and primary == "claude" and fallbacks) else primary)
    q6 = {
        "question": "6. Budget & fallback status?",
        "used_tokens": used_tokens,
        "token_budget": token_budget,
        "used_calls": used_calls,
        "call_budget": WEEKLY_CALL_BUDGET,
        "fallback_active": over_budget,
        "fallbacks": fallbacks,
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
