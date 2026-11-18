"""`lifeos lint`: check task files before they cost you a bad hand-off.

Every tasks/T-*.md needs the front matter the template creates: id (same as the file name), goal, a real done_when (not
the TODO placeholder), a valid level (L0-L3), status and due date. A task marked done needs proof (rule 1): a link, a test
name or a path under `## Proof`. Read-only.
"""
import re
from pathlib import Path

from .tasks import read_frontmatter

STATUSES = {"inbox", "todo", "doing", "blocked", "done"}
REQUIRED = ("id", "goal", "done_when", "route", "level", "status")


def _proof_section(text):
    m = re.search(r"(?ms)^## Proof\s*\n(.*?)(?=^## |\Z)", text)
    return (m.group(1) if m else "").strip()


def _has_proof(text):
    body = text.split("## Proof", 1)[1] if "## Proof" in text else ""
    return bool(re.search(r"https?://|\b[\w/.-]+\.(?:py|md|csv|json|html)\b|pytest|\bPR\b|#\d+", body))


def check(home):
    out = []
    for path in sorted((Path(home) / "tasks").glob("T-*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        name = path.stem

        def bad(problem):
            out.append({"task": name, "problem": problem})
        if not text.startswith("---\n"):
            bad("frontmatter: the file has no --- front matter block")
            continue
        f = read_frontmatter(path)
        for key in REQUIRED:
            if not f.get(key):
                bad(f"{key}: missing")
        if f.get("id") and f["id"] != name:
            bad(f"id: '{f['id']}' does not match the file name")
        if f.get("done_when", "").startswith("TODO"):
            bad("done_when: still the TODO placeholder")
        if f.get("level") and not re.match(r"L[0-3](?:\s|$)", f["level"]):
            bad(f"level: '{f['level']}' is not one of L0-L3")
        if f.get("status") and f["status"] not in STATUSES:
            bad(f"status: '{f['status']}' is not one of {', '.join(sorted(STATUSES))}")
        if f.get("due") and not re.fullmatch(r"\d{4}-\d\d-\d\d", f["due"]):
            bad(f"due: '{f['due']}' is not YYYY-MM-DD")
        if f.get("status") == "done" and not _has_proof(text):
            bad("proof: marked done but no link, file or test under ## Proof (rule 1)")
    return out


def render(found):
    if not found:
        return "tasks ok: no problems."
    return "\n".join(f"{p['task']}  {p['problem']}" for p in found) + f"\n\n{len(found)} problem(s)."
