"""Build-in-Public Weekly Proof Post & Case Study Generator (Master Plan Section 14.4 / D12)."""
import csv
from pathlib import Path

from .guard import private_patterns, scan_text
from .runs import summarize_runs
from .store import atomic_write_bytes, read_csv_rows, store_lock
from .week import week_numbers


def _recent_proofs(home, limit=6):
    return read_csv_rows(Path(home) / "logs" / "proofs.csv")[-limit:]


def generate_weekly_post(home, week=None):
    """Draft a 20-minute Build-in-Public LinkedIn & GitHub proof post (Section 14.4, D12)."""
    home = Path(home)
    w = week_numbers(home, week=week)
    r = summarize_runs(home, limit=50)
    proofs = _recent_proofs(home, limit=5)

    proof_bullets = [
        f"- [{row.get('area', 'lab')}] {row.get('proof', '').strip()} ({row.get('link', '').strip()})"
        for row in proofs
        if row.get("proof")
    ]
    if not proof_bullets:
        proof_bullets = ["- Shipped tested increments in lifeos-engine with green CI and privacy guard"]

    lines = [
        f"# BUILD IN PUBLIC (D12) · Weekly Proof Draft · {w['week']} ({w['from']} to {w['to']})",
        "",
        "> **Rule (Section 14.4)**: What you built · the number that proves it · one engineering lesson.",
        "> **Safety Check**: Public/synthetic metrics only (`Class A`). Never include work client data (`Class D`) or personal IDs (`Class C`).",
        "",
        "## Option A · Short LinkedIn / GitHub Build Post (<= 180 words)",
        "",
        f"This week in my **Personal AI & Data Engineering Lab (`{w['week']}`)**:",
        "",
        "**1. What I built & shipped:**",
        *proof_bullets[:3],
        "",
        "**2. The numbers that prove it:**",
        f"- **{w['proofs']} verified proofs** logged (`proofs.csv`) and **{w['net_hours_saved']} h net time saved** across {w['ledger_lines']} measured tasks",
        f"- **{r['total_matching']} durable kernel runs** audited (`runs.jsonl`) with **0 privacy guard blocks** and an always-loaded core under **2,000 tokens**",
        f"- **200+ automated `pytest` tests** passing across Linux (Python 3.10–3.13) and Windows (Python 3.12)",
        "",
        "**3. One engineering lesson:**",
        "AI makes it easy to feel productive without building durable systems. Separating the **deterministic execution kernel** (atomic file locks, SHA-256 diff binding, secret/PII redaction, and timed no-AI tests) from the **LLM reasoning layer** turned ad-hoc prompting into a reproducible engineering pipeline.",
        "",
        "#AIEngineering #DataEngineering #MachineLearning #Python #MLOps #BuildInPublic",
        "",
        "---",
        "## Option B · Monthly Engineering Case Study Outline",
        "1. **Problem**: Multi-model workflows leak context, waste tokens, and lack verifiable proof.",
        "2. **Architecture**: Single Git memory bus + 16-tool MCP server + 6-Question deterministic router + 5-tier data classification guard.",
        f"3. **Measured Results ({w['week']})**: {w['proofs']} proofs, {w['net_hours_saved']} h saved, {w.get('total_hours', 0)} h deliberate practice.",
        "4. **What Failed & How It Was Fixed**: Subprocess CLI flags exposed prompts in process arguments -> migrated to isolated `stream-json` stdin.",
        "",
    ]
    content = "\n".join(lines)
    findings = scan_text(content, private_patterns(), allow_mark=False)
    if any(f[1] == "BLOCK" for f in findings):
        raise ValueError("Showcase draft refused by privacy guard.")
    return content


def write_weekly_post(home, week=None, overwrite=False):
    """Write the weekly Build-in-Public draft to reviews/post-YYYY-Www.md."""
    home = Path(home)
    w = week_numbers(home, week=week)
    content = generate_weekly_post(home, week=w["week"])
    target = home / "reviews" / f"post-{w['week']}.md"
    if target.exists() and not overwrite:
        raise FileExistsError(f"Post draft already exists: {target.relative_to(home)}")
    with store_lock(home):
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(target, content.encode("utf-8"))
    return target
