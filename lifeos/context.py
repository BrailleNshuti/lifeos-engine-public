"""Context packs: the smallest set of LifeOS files a model needs, with a token estimate, provenance and a budget."""
import hashlib
import re
import subprocess
from pathlib import Path

from .home import estimate_tokens

PRIORITY = ("rules.md", "TASK", "now.md", "me.md")
TASK_FIRST = ("TASK", "rules.md", "now.md", "me.md")


def pack_hash(text):
    """Full 64-character deterministic SHA-256 hex digest of a context pack or file."""
    norm = "\n".join(line.rstrip() for line in (text or "").replace("\r\n", "\n").splitlines())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def task_file(home, task_id):
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


def _validate_budget(budget):
    if isinstance(budget, bool) or not isinstance(budget, int) or not 1 <= budget <= 50000:
        raise ValueError("Context budget must be an integer from 1 to 50000 tokens.")


def build_pack(home, task_id=None, budget=6000, task_first=False, names=None):
    """Return (pack_text, token_estimate). Files are added in priority order; the last ones are trimmed to fit."""
    _validate_budget(budget)
    home = Path(home)
    files = []
    for name in (TASK_FIRST if task_first else PRIORITY):
        if names is not None and name not in names:
            continue
        if name == "TASK":
            if task_id:
                path = task_file(home, task_id)
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


def explain_pack(home, task_id=None, budget=6000, task_first=False, names=None):
    """Return provenance, inclusion status, token cost and full SHA-256 digests for every candidate context source."""
    _validate_budget(budget)
    home = Path(home)
    order = TASK_FIRST if task_first else PRIORITY
    items, used, full = [], 0, False
    for name in order:
        if name == "TASK":
            if not task_id:
                continue
            path = task_file(home, task_id)
            label = f"tasks/{path.name}"
        else:
            path = home / name
            label = name
        if names is not None and name not in names:
            items.append({"name": label, "status": "excluded (minimal mode)", "tokens": 0, "sha256": "-"})
            continue
        if not path.exists():
            items.append({"name": label, "status": "missing", "tokens": 0, "sha256": "-"})
            continue
        text = path.read_text(encoding="utf-8")
        digest = pack_hash(text)
        if full:
            items.append({"name": label, "status": "excluded (budget full)", "tokens": 0, "sha256": digest})
            continue
        block = f"=== {label} ===\n{text.strip()}\n"
        cost = estimate_tokens(block)
        if used + cost <= budget:
            items.append({"name": label, "status": "included", "tokens": cost, "sha256": digest})
            used += cost
            continue
        room_chars = (budget - used) * 4 - 80
        if used == 0:
            room_chars = max(room_chars, 200)
        if used == 0 or room_chars > 400:
            trimmed = f"=== {label} (trimmed to fit {budget} tokens) ===\n{text.strip()[:room_chars]}\n"
            t_cost = estimate_tokens(trimmed)
            items.append({"name": label, "status": "trimmed", "tokens": t_cost, "sha256": digest})
            used += t_cost
        else:
            items.append({"name": label, "status": "excluded (budget full)", "tokens": 0, "sha256": digest})
        full = True
    pack, total = build_pack(home, task_id, budget, task_first=task_first, names=names)
    return {"budget": budget, "tokens": total, "sha256": pack_hash(pack), "items": items}


def render_explanation(info):
    lines = [f"Context pack · {info['tokens']} / {info['budget']} tokens · sha256 {info['sha256']}"]
    for item in info["items"]:
        lines.append(f"  {item['status']:<24} {item['name']:<32} ~{item['tokens']:>4} tokens  {item['sha256']}")
    return "\n".join(lines)


def inspect_repo_commit(repo_path, commit="HEAD"):
    """Resolve exact repository commit SHA, branch, tracked file list, and unified diff for blind review."""
    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        raise FileNotFoundError(f"Repository path not found: {repo_path}")

    def _git(*args):
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
        if proc.returncode != 0:
            raise ValueError(f"git {' '.join(args)} failed in {repo}: {proc.stderr.strip()[:200]}")
        return proc.stdout.strip()

    commit_sha = _git("rev-parse", "--verify", f"{commit}^{{commit}}")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    stat = _git("show", "--stat", "--format=fuller", commit_sha)
    files = _git("ls-tree", "--name-only", "-r", commit_sha)
    patch = _git("show", "--format=", commit_sha)
    meta = (
        f"repo: {repo.name} ({repo.as_posix()})\n"
        f"branch: {branch}\n"
        f"commit_sha: {commit_sha}\n\n"
        f"--- commit summary ---\n{stat}\n\n"
        f"--- tracked files ({len(files.splitlines())}) ---\n{files}"
    )
    return {
        "repo": repo,
        "branch": branch,
        "commit_sha": commit_sha,
        "meta_text": meta,
        "diff_text": patch,
    }


def build_review_pack(home, task_id, budget=6000, diff_text="", repo_info=None):
    """Facts-only pack for blind review (rule 7): strips any appended '## Result · ...' blocks so reviewers never see prior answers,
    and reserves budget so repository metadata and commit diffs always reach reviewers."""
    _validate_budget(budget)
    has_diff = bool((repo_info and repo_info.get("diff_text", "").strip()) or diff_text.strip())
    if (repo_info or has_diff) and budget < 80:
        raise ValueError(f"Review budget ({budget} tokens) is too small to include repository metadata and commit diff.")
    home = Path(home)
    path = task_file(home, task_id)
    facts = re.split(r"\n## Result\s*·", path.read_text(encoding="utf-8"), maxsplit=1)[0].strip()
    parts = [(f"tasks/{path.name} (facts only)", facts)]
    if (home / "rules.md").exists():
        parts.append(("rules.md", (home / "rules.md").read_text(encoding="utf-8").strip()))
    if repo_info:
        parts.append((f"repo_commit ({repo_info['commit_sha'][:12]})", repo_info["meta_text"].strip()))
        if repo_info.get("diff_text", "").strip():
            parts.append((f"commit_diff ({repo_info['commit_sha'][:12]})", repo_info["diff_text"].strip()))
    if diff_text.strip():
        parts.append(("diff", diff_text.strip()))

    full_costs = [estimate_tokens(f"=== {n} ===\n{t}\n") for n, t in parts]
    if sum(full_costs) <= budget:
        blocks = [f"=== {n} ===\n{t}\n" for n, t in parts]
        pack = "\n".join(blocks)
        return pack, estimate_tokens(pack)

    blocks, used = [], 0
    total_parts = len(parts)
    for idx, (name, text) in enumerate(parts):
        block = f"=== {name} ===\n{text}\n"
        cost = full_costs[idx]
        # Reserve space for every subsequent section (especially repo_commit and commit_diff/diff)
        reserved = 0
        for rem_idx in range(idx + 1, total_parts):
            rem_name = parts[rem_idx][0]
            min_share = max(50, budget // 4) if ("diff" in rem_name or "repo_commit" in rem_name) else max(25, budget // (total_parts + 1))
            reserved += min(full_costs[rem_idx], min_share)
        avail = max(20, budget - used - reserved)
        if cost <= avail:
            blocks.append(block)
            used += cost
            continue
        header = f"=== {name} (trimmed to fit {budget} tokens) ===\n"
        room = max(avail * 4 - len(header) - 8, 40)
        trimmed_block = f"{header}{text[:room]}\n"
        blocks.append(trimmed_block)
        used += estimate_tokens(trimmed_block)
    pack = "\n".join(blocks)
    return pack, estimate_tokens(pack)
