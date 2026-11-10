"""Context packs: the smallest set of LifeOS files a model needs, with a token estimate and a budget."""
from pathlib import Path

from .home import estimate_tokens

PRIORITY = ("rules.md", "TASK", "now.md", "me.md")


def _task_file(home, task_id):
    matches = sorted((Path(home) / "tasks").glob(f"{task_id}*.md"))
    if not matches:
        raise FileNotFoundError(f"Task {task_id} not found in tasks/.")
    return matches[0]


def build_pack(home, task_id=None, budget=6000):
    """Return (pack_text, token_estimate). Files are added in priority order; the last ones are trimmed to fit."""
    home = Path(home)
    files = []
    for name in PRIORITY:
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
