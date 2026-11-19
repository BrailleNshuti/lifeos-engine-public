"""Quarterly Blind Role Bake-Off Engine."""
from datetime import date
import hashlib
import json
from pathlib import Path
import re

from .guard import private_patterns, scan_text
from .store import atomic_write_bytes, store_lock


def blind_pair(quarter, task_type, model_a, model_b):
    """Deterministically assign Model A and Model B to hidden labels X and Y using a SHA-256 digest."""
    seed = f"{quarter}:{task_type}:{model_a}:{model_b}".encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()
    swap = int(digest[0], 16) % 2 == 1
    if swap:
        return {"X": model_b, "Y": model_a, "blind_hash": digest[:12]}
    return {"X": model_a, "Y": model_b, "blind_hash": digest[:12]}


def render_bakeoff_card(quarter, task_type, model_a="claude", model_b="chatgpt", scores=None):
    """Render a Role Bake-Off scorecard (keeping X/Y anonymized until scores are provided)."""
    mapping = blind_pair(quarter, task_type, model_a, model_b)
    lines = [
        f"# ROLE BAKE-OFF · {quarter} · task type: {task_type}",
        "",
        f"Same facts-only prompt given to two models; names hidden as **X** and **Y** (blind seal `{mapping['blind_hash']}`).",
        "",
        "| Blind ID | Task # | Correct (1-5) | Useful (1-5) | Sourced (1-5) | Time (1-5) | Total (/20) |",
        "|---|---|---|---|---|---|---|",
    ]

    totals = {"X": 0, "Y": 0}
    wins = {"X": 0, "Y": 0}

    if scores:
        for task_idx in (1, 2, 3):
            t_key = f"t{task_idx}"
            row_x = scores.get("X", {}).get(t_key, [4, 4, 4, 4])
            row_y = scores.get("Y", {}).get(t_key, [3, 4, 3, 4])
            sum_x = sum(row_x)
            sum_y = sum(row_y)
            totals["X"] += sum_x
            totals["Y"] += sum_y
            if sum_x > sum_y:
                wins["X"] += 1
            elif sum_y > sum_x:
                wins["Y"] += 1
            lines.append(f"| **X** | Task {task_idx} | {row_x[0]} | {row_x[1]} | {row_x[2]} | {row_x[3]} | **{sum_x}** |")
            lines.append(f"| **Y** | Task {task_idx} | {row_y[0]} | {row_y[1]} | {row_y[2]} | {row_y[3]} | **{sum_y}** |")
    else:
        for blind_id in ("X", "Y"):
            for task_idx in (1, 2, 3):
                lines.append(f"| **{blind_id}** | Task {task_idx} | __ | __ | __ | __ | __ |")

    lines.extend([
        "",
        "## Verdict & Seal Reveal",
    ])
    if scores:
        winner_id = "X" if (wins["X"] > wins["Y"] or (wins["X"] == wins["Y"] and totals["X"] >= totals["Y"])) else "Y"
        winner_model = mapping[winner_id]
        lines.extend([
            f"- **Unsealed Mapping**: `X = {mapping['X']}` · `Y = {mapping['Y']}`",
            f"- **Task Wins**: X won {wins['X']}/3 ({totals['X']} pts) · Y won {wins['Y']}/3 ({totals['Y']} pts)",
            f"- **Winner (2 of 3 rule)**: **`{winner_model}`** (`{winner_id}`) becomes the default for `{task_type}`; update `rules.md` and `system/roles.md`.",
        ])
    else:
        lines.extend([
            "- Score all 3 tasks for X and Y **before** unsealing model identities.",
            "- Winner of 2 of 3 becomes the default; update `rules.md` and `system/roles.md`.",
        ])
    lines.append("")
    return "\n".join(lines)


def write_bakeoff(home, quarter=None, task_type="Decision Memo", model_a="claude", model_b="chatgpt", scores_json=None, overwrite=False):
    """Write a Role Bake-Off scorecard to reviews/bakeoff-YYYY-Qn.md."""
    home = Path(home)
    today = date.today()
    q_num = ((today.month - 1) // 3) + 1
    q_str = quarter or f"{today.year}-Q{q_num}"
    if not re.match(r"^\d{4}-Q[1-4]$", q_str):
        raise ValueError(f"Invalid quarter '{q_str}'; expected YYYY-Q1..Q4.")
    scores = json.loads(scores_json) if scores_json else None
    content = render_bakeoff_card(q_str, task_type, model_a=model_a, model_b=model_b, scores=scores)
    findings = scan_text(content, private_patterns(), allow_mark=False)
    if any(f[1] == "BLOCK" for f in findings):
        raise ValueError("Bake-off scorecard refused by privacy guard.")
    slug = re.sub(r"[^a-z0-9]+", "-", task_type.lower()).strip("-")
    target = home / "reviews" / f"bakeoff-{q_str}-{slug}.md"
    if target.exists() and not overwrite:
        raise FileExistsError(f"Bake-off file already exists: {target.relative_to(home)}")
    with store_lock(home):
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(target, content.encode("utf-8"))
    return target
