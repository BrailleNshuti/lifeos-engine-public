"""Context packs: the smallest set of LifeOS files a model needs, with a token estimate and a budget."""
import re
from pathlib import Path

from .home import estimate_tokens

PRIORITY = ("rules.md", "TASK", "now.md", "me.md")
TASK_FIRST = ("TASK", "rules.md", "now.md", "me.md")


def _task_file(home, task_id):
    if not re.fullmatch(r"T-[A-Za-z0-9-]+", task_id or ""):
        raise ValueError(f"'{task_id}' is not a task id (expected something like T-261116 or T-261116-demo-cli).")
    folder = Path(home) / "tasks"
    if (folder / f"{task_id}.md").exists():
        return folder / f"{task_id}.md"
    matches = sorted(folder.glob(f"{task_id}*.md"))
    if not matches:
        raise FileNotFoundError(f"Task {task_id} not found in tasks/.")
    if len(matches) > 1:
        raise ValueError(f"'{task_id}' matches {len(matches)} tasks ({', '.join(m.stem for m in matches)}). Use the full id.")
    return matches[0]


def build_pack(home, task_id=None, budget=6000, task_first=False, names=None):
    """Return (pack_text, token_estimate). Files are added in priority order; the last ones are trimmed to fit."""
    home = Path(home)
    files = []
    for name in (TASK_FIRST if task_first else PRIORITY):
        if names is not None and name not in names:
            continue
        if name == "TASK":
            if task_id:
                path = _task_file(home, task_id)
                files.append((f"tasks/{path.name}", path.read_text(encoding="utf-8")))
        elif (home / name).exists():
            files.append((name, (home / name).read_text(encoding="utf-8")))

    blocks, used = [], 0
    for name, text in files:
        block = f"=== {name} ===\n{text.strip()}\n"
        cost = estimate_tokens(block)
        if used + cost <= budget:
            blocks.append(block)
            used += cost
            continue
        room_chars = (budget - used) * 4 - 80
        if not blocks:  # the most important file always goes in, trimmed if it must be
            room_chars = max(room_chars, 200)
        if not blocks or room_chars > 400:
            blocks.append(f"=== {name} (trimmed to fit {budget} tokens) ===\n{text.strip()[:room_chars]}\n")
        break
    pack = "\n".join(blocks)
    return pack, estimate_tokens(pack)
