"""Task files: one hand-off file per job, created from one sentence."""
import datetime as dt
import re
from pathlib import Path

STOP_WORDS = {"the", "a", "an", "to", "of", "and", "for", "in", "on", "my", "with", "at", "by", "from", "into"}

TEMPLATE = """---
id: {id}
goal: {goal}
done_when: TODO (you write this line)
route: {route}
level: {level}
status: inbox
due: {due}
---
## Context (links, not essays)

## Task
{goal}

## Result (written back here)
What was done · evidence (links, tests, sources with dates) · open issues · next step

## Proof

## Ledger: minutes spent __ | saved ~__ | quality __/5
"""


def slugify(text, max_words=4):
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP_WORDS]
    return "-".join(words[:max_words]) or "task"


def new_task(home, sentence, today=None, route="Claude Code -> Codex review", level="L2", due=""):
    """Create tasks/T-YYMMDD-slug.md and return its path. Never overwrites an existing file."""
    sentence = sentence.strip()
    if not sentence:
        raise ValueError("The task needs one sentence.")
    today = today or dt.date.today()
    base = f"T-{today:%y%m%d}-{slugify(sentence)}"
    folder = Path(home) / "tasks"
    folder.mkdir(exist_ok=True)
    path, n = folder / f"{base}.md", 2
    while path.exists():
        path, n = folder / f"{base}-{n}.md", n + 1
    goal = sentence.rstrip(".")
    path.write_text(TEMPLATE.format(id=path.stem, goal=goal, route=route, level=level, due=due), encoding="utf-8")
    return path


def read_frontmatter(path):
    text = Path(path).read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", text, re.S)
    fields = {}
    if match:
        for line in match.group(1).splitlines():
            if ":" in line and not line.startswith((" ", "\t")):
                key, value = line.split(":", 1)
                fields[key.strip()] = value.split(" #")[0].strip()
    return fields


def list_tasks(home, status=None):
    rows = []
    for path in sorted((Path(home) / "tasks").glob("T-*.md")):
        fields = read_frontmatter(path)
        if status and fields.get("status") != status:
            continue
        rows.append({"id": path.stem, "status": fields.get("status", ""), "due": fields.get("due", ""),
                     "goal": fields.get("goal", "")})
    return rows
