"""Monthly No-AI Exam generator and strict rubric recorder."""
from datetime import date
from pathlib import Path
import re

from .guard import private_patterns, scan_text
from .log import log_proof
from .store import atomic_write_bytes, store_lock

EXAM_BANK = {
    "Python engineering": {
        "short": "Explain the difference between an iterator and a generator in Python, and why `with` context managers guarantee resource cleanup even when an exception is raised.",
        "problem": "Given a list of dictionaries `[{'area': 'study', 'hours': 1.5}, ...]`, write a pure function `group_hours(rows)` using `collections.defaultdict` or `itertools` that returns total hours per area sorted descending by hours, in O(n log k) time.",
        "code": "On paper / in a blank file without AI: write a complete CLI module using `argparse` and `pathlib` that reads a CSV file, validates that no row has an empty required column, and exits with code 2 on validation failure.",
        "oral": "Explain how `pytest` fixtures (`tmp_path`, `monkeypatch`, `capsys`) isolate unit tests from the host filesystem and subprocesses.",
    },
    "SQL and data modelling": {
        "short": "Contrast 3NF OLTP schemas with Star-Schema OLAP marts, and explain why Slowly Changing Dimension Type 2 (SCD2) is required when auditing historical rent against changing unit prices.",
        "problem": "Write a SQL query using `LAG()` and `SUM() OVER (...)` that computes each month's confirmed revenue, the month-over-month delta, and the 3-month rolling average.",
        "code": "Write an anti-join query (`LEFT JOIN ... WHERE ... IS NULL`) that finds all active leases with zero confirmed payments in `'2026-11'`, and write the composite B-Tree index that optimizes it.",
        "oral": "Explain the Leftmost Prefix Rule for a composite index on `(lease_id, billing_month, status)`.",
    },
    "Cloud and infrastructure": {
        "short": "State the NIST 5-3-4 Cloud definition and explain the exact security difference between Linux `namespaces` and `cgroups`.",
        "problem": "A data pipeline has a 12% sequential fraction (s = 0.12). Using Amdahl's Law, compute the maximum theoretical speedup as N -> infinity and the speedup at N = 8 workers.",
        "code": "Write a Terraform resource block or IAM Bucket Policy that restricts `s3:GetObject` on a private bucket strictly to an Amazon CloudFront Origin Access Control (OAC) distribution ARN.",
        "oral": "Walk through KMS Envelope Encryption (CMK vs DEK) and explain why a 50 GB file is never sent directly to the KMS API.",
    },
    "Deep learning (PyTorch)": {
        "short": "Explain why `optimizer.zero_grad()`, `model.eval()`, and `torch.no_grad()` are each required in a PyTorch training/validation loop, and what breaks if any one of them is omitted.",
        "problem": "Given input x = [2, 1], weights w1 = [0.5, -1.0], b1 = 0, w2 = 1.0, b2 = 0, sigmoid activations, and binary cross-entropy loss with target y = 1: compute the forward pass (a1, y_hat) and backward gradient dL/dw2 by hand.",
        "code": "Write a complete single-epoch PyTorch training function `train_one_epoch(model, loader, criterion, optimizer, device)` including gradient norm clipping (`max_norm=1.0`).",
        "oral": "Explain Scaled Dot-Product Attention `softmax(QK^T / sqrt(d_k))V` and why we divide by `sqrt(d_k)`.",
    },
    "Software practice": {
        "short": "Draw Marick's Testing Quadrant (Q1–Q4) across its two axes (Technology vs Business facing; Support Programming vs Critique Product) and place Unit tests, Property/BDD tests, Exploratory tests, and Load/Security tests.",
        "problem": "Compare TDD, ATDD, and BDD across primary focus, collaboration audience, and automation layer, and state the 3 pillars of Testing Machine Learning Systems.",
        "code": "Write an architectural layering test in `pytest` using Python's `ast` module that fails if any core module imports `mcp_server` or `cli`.",
        "oral": "Explain Experimental-Operational Symmetry in ML systems and how Population Stability Index (PSI >= 0.25) detects production data drift.",
    },
}


def _read_skills_rows(home):
    p = Path(home) / "logs" / "skills.md"
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6 or cells[0].lower() in ("skill", "---") or set(cells[0]) <= {"-"}:
            continue
        rows.append(cells)
    return rows


def generate_monthly_exam(home, month=None, module="Core module"):
    """Build a deterministic 60-90 min Monthly No-AI Exam."""
    home = Path(home)
    month_str = month or date.today().strftime("%Y-%m")
    skills_rows = _read_skills_rows(home)
    selected_topics = [r[0] for r in skills_rows if r[0] in EXAM_BANK]
    if not selected_topics:
        selected_topics = list(EXAM_BANK.keys())[:3]

    t1 = selected_topics[0 % len(selected_topics)]
    t2 = selected_topics[1 % len(selected_topics)]
    t3 = selected_topics[2 % len(selected_topics)]
    t4 = selected_topics[3 % len(selected_topics)]
    t5 = selected_topics[4 % len(selected_topics)]

    lines = [
        f"# MONTHLY NO-AI EXAM · {month_str}",
        "",
        "> **Protocol**: 60 to 90 minutes, **strictly offline / zero AI**.",
        "> Write your answers in this file or on paper first. Any topic scoring **< 70%** automatically returns next month.",
        f"> **Focus Module**: `{module}`",
        "",
        "## Part 1 · Three Short-Answer Retrieval Questions (30 pts — 10 pts each)",
        f"1. **[{t1}]** {EXAM_BANK[t1]['short']}",
        f"2. **[{t2}]** {EXAM_BANK[t2]['short']}",
        f"3. **[{t3}]** {EXAM_BANK[t3]['short']}",
        "",
        "## Part 2 · Two Quantitative / Derivation Problems (30 pts — 15 pts each)",
        f"4. **[{t4}]** {EXAM_BANK[t4]['problem']}",
        f"5. **[{t2}]** {EXAM_BANK[t2]['problem']}",
        "",
        "## Part 3 · Timed From-Scratch Code Task (25 pts — No AI, No Autocomplete)",
        f"6. **[{t1}]** {EXAM_BANK[t1]['code']}",
        "",
        "## Part 4 · Explain-It-Aloud / Oral Question (15 pts — 5-Minute Recording)",
        f"7. **[{t5}]** {EXAM_BANK[t5]['oral']}",
        "",
        "---",
        "## Strict Grading Rubric & Score Record",
        "| Section | Max Points | Awarded | Weakest Point / Error Note |",
        "|---|---|---|---|",
        "| Part 1 (Short Answers Q1–Q3) | 30 | __ | |",
        "| Part 2 (Problems Q4–Q5) | 30 | __ | |",
        "| Part 3 (Code Task Q6) | 25 | __ | |",
        "| Part 4 (Oral Explanation Q7) | 15 | __ | |",
        "| **Total Score (%)** | **100** | **__ %** | **Pass bar >= 70% (top-grade bar >= 96%)** |",
        "",
        "## Three Weakest Points to Repeat Next Month",
        "1. ",
        "2. ",
        "3. ",
        "",
    ]
    return "\n".join(lines)


def write_exam_draft(home, month=None, module="Core module", overwrite=False):
    """Write the monthly no-AI exam paper to reviews/exam-YYYY-MM.md under the repo lock."""
    home = Path(home)
    month_str = month or date.today().strftime("%Y-%m")
    if not re.match(r"^\d{4}-\d{2}$", month_str):
        raise ValueError(f"Invalid month '{month_str}'; expected YYYY-MM.")
    content = generate_monthly_exam(home, month=month_str, module=module)
    findings = scan_text(content, private_patterns(), allow_mark=False)
    blocks = [f for f in findings if f[1] == "BLOCK"]
    if blocks:
        raise ValueError("Refused by privacy guard.")
    target = home / "reviews" / f"exam-{month_str}.md"
    if target.exists() and not overwrite:
        raise FileExistsError(f"Exam file already exists: {target.relative_to(home)} (refusing to overwrite).")
    with store_lock(home):
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(target, content.encode("utf-8"))
    return target


def record_exam_score(home, skill_name, score_pct, proof_link="reviews/exam.md"):
    """Update logs/skills.md with the latest timed no-AI exam percentage and log a proof row."""
    home = Path(home)
    pct = int(score_pct)
    if pct < 0 or pct > 100:
        raise ValueError("Exam score percentage must be between 0 and 100.")
    skills_path = home / "logs" / "skills.md"
    if not skills_path.exists():
        skills_path.parent.mkdir(parents=True, exist_ok=True)
        default_rows = [
            "# Skills",
            "| skill | level 1-5 | target Nov 2027 | proof (link) | last deliberate practice | next small proof | last exam % |",
            "|---|---|---|---|---|---|---|",
            *[f"| {k} | 1 | 4 | | | | |" for k in EXAM_BANK],
        ]
        skills_path.write_text("\n".join(default_rows) + "\n", encoding="utf-8")

    today = date.today().isoformat()
    updated = False
    out_lines = []
    for line in skills_path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 7 and cells[0].lower() == skill_name.strip().lower():
                lvl = int(cells[1]) if cells[1].isdigit() else 1
                if pct >= 80 and lvl < 3:
                    lvl = 3
                cells[1] = str(lvl)
                cells[4] = today
                cells[6] = f"{pct}%"
                line = "| " + " | ".join(cells) + " |"
                updated = True
        out_lines.append(line)

    if not updated:
        raise ValueError(f"Skill '{skill_name}' not found in logs/skills.md.")

    with store_lock(home):
        atomic_write_bytes(skills_path, ("\n".join(out_lines) + "\n").encode("utf-8"))
    log_proof(home, "study", f"No-AI Exam ({skill_name}): {pct}%", proof_link)
    return {"skill": skill_name, "score_pct": pct, "elevated_to_level_3": pct >= 80}
