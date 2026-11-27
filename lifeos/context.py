"""Context packs: the smallest set of LifeOS files a model needs, with a token estimate, provenance and a budget."""
import hashlib
import re
import subprocess
from pathlib import Path

from .home import estimate_tokens
from .store import read_text_retry

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


def visible_task(text):
    """Drop ## Route notes. They stay in the task file and out of the next prompt."""
    kept = []
    skipping = False
    for line in (text or "").replace("\r\n", "\n").splitlines():
        if line.startswith("## Route"):
            skipping = True
            continue
        if skipping and line.startswith("## "):
            skipping = False
        if not skipping:
            kept.append(line)
    body = "\n".join(kept).strip()
    return f"{body}\n" if body else ""

ATTACH_EXT = (".md", ".txt")
ATTACH_MAX_FILES = 4
ATTACH_MAX_TOKENS = 3000
ATTACH_BLOCKED = ("logs", ".git", ".github")


def _context_section(task_text):
    lines, inside = [], False
    for line in (task_text or "").replace("\r\n", "\n").splitlines():
        if line.startswith("## "):
            inside = line.startswith("## Context")
            continue
        if inside:
            lines.append(line)
    return lines


def context_attachments(home, task_id):
    """Files the task lists under '## Context', as [(label, text)]. Only notes (.md/.txt) inside the data
    repository qualify: no '..', no absolute paths, no symlink escape, nothing under logs/ or .git. At most four
    files, each cut to a token cap. Lines that are not an existing file are plain text and ignored."""
    if not task_id:
        return []
    home = Path(home).resolve()
    out, seen = [], set()
    for raw in _context_section(read_text_retry(task_file(home, task_id))):
        line = raw.strip().lstrip("-*+ ").strip().strip("`").lstrip("@").strip().replace("\\", "/")
        if not line or line.startswith("/") or ":" in line or ".." in line.split("/"):
            continue
        if not line.lower().endswith(ATTACH_EXT) or line.split("/")[0].lower() in ATTACH_BLOCKED:
            continue
        path = home / line
        try:
            real = path.resolve(strict=True)
            rel = real.relative_to(home).as_posix()
        except (OSError, ValueError):
            continue
        if not real.is_file() or rel in seen or rel.split("/")[0].lower() in ATTACH_BLOCKED or rel in PRIORITY:
            continue
        seen.add(rel)
        text = read_text_retry(real, errors="replace")
        limit = ATTACH_MAX_TOKENS * 4
        if len(text) > limit:
            text = text[:limit]
        out.append((f"{rel} (attached)", text))
        if len(out) == ATTACH_MAX_FILES:
            break
    return out


def build_pack(home, task_id=None, budget=6000, task_first=False, names=None, task_limit=None):
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
                files.append((f"tasks/{path.name}", visible_task(read_text_retry(path)[:task_limit])))
        elif (home / name).exists():
            files.append((name, read_text_retry(home / name)))
    if task_id:
        files.extend(context_attachments(home, task_id))

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


def explain_pack(home, task_id=None, budget=6000, task_first=False, names=None, task_limit=None):
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
        text = read_text_retry(path)
        if name == "TASK":
            text = visible_task(text[:task_limit])
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
    for label, text in (context_attachments(home, task_id) if task_id else []):
        digest = pack_hash(text)
        block = f"=== {label} ===\n{text.strip()}\n"
        cost = estimate_tokens(block)
        if not full and used + cost <= budget:
            items.append({"name": label, "status": "included", "tokens": cost, "sha256": digest})
            used += cost
            continue
        room_chars = (budget - used) * 4 - 80
        if not full and room_chars > 400:
            trimmed = f"=== {label} (trimmed to fit {budget} tokens) ===\n{text.strip()[:room_chars]}\n"
            items.append({"name": label, "status": "trimmed", "tokens": estimate_tokens(trimmed), "sha256": digest})
            used += estimate_tokens(trimmed)
        else:
            items.append({"name": label, "status": "excluded (budget full)", "tokens": 0, "sha256": digest})
        full = True
    pack, total = build_pack(home, task_id, budget, task_first=task_first, names=names, task_limit=task_limit)
    return {"budget": budget, "tokens": total, "sha256": pack_hash(pack), "items": items}


def render_explanation(info):
    lines = [f"Context pack · {info['tokens']} / {info['budget']} tokens · sha256 {info['sha256']}"]
    for item in info["items"]:
        lines.append(f"  {item['status']:<24} {item['name']:<32} ~{item['tokens']:>4} tokens  {item['sha256']}")
    return "\n".join(lines)


COMMIT_META_FORMAT = "commit %H%nparents %P%nauthor_date %aI%ncommit_date %cI%n%n    %s%n"


def inspect_repo_commit(repo_path, commit="HEAD"):
    """Resolve exact repository commit SHA, branch, tracked file list, and unified diff for blind review
    using an explicit identity-free format (no author/committer names or emails)."""
    if not isinstance(commit, str) or not commit.strip():
        raise ValueError("commit must be a non-empty string.")
    commit = commit.strip()
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
    has_parent = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"{commit_sha}^1"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    ).returncode == 0
    if has_parent:
        stat = _git("show", "--first-parent", "-m", "--stat", f"--format={COMMIT_META_FORMAT}", commit_sha)
        patch = _git("diff", f"{commit_sha}^1", commit_sha)
    else:
        stat = _git("show", "--root", "--stat", f"--format={COMMIT_META_FORMAT}", commit_sha)
        patch = _git("show", "--root", "--format=", commit_sha)
    files = _git("ls-tree", "--name-only", "-r", commit_sha)
    # The resolved path is retained in repo_info["repo"] for local worktree
    # operations only. It must never enter a review pack: absolute paths can
    # disclose the OS username or private directory names to a remote model.
    meta = (
        f"repo: {repo.name}\n"
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
    and reserves budget so repository metadata and commit diffs always reach reviewers within `budget` tokens."""
    _validate_budget(budget)
    has_diff = bool((repo_info and repo_info.get("diff_text", "").strip()) or diff_text.strip())
    home = Path(home)
    path = task_file(home, task_id)
    facts = re.split(r"\n## Result\s*·", visible_task(read_text_retry(path)), maxsplit=1)[0].strip()
    parts = [(f"tasks/{path.name} (facts only)", facts)]
    if (home / "rules.md").exists():
        parts.append(("rules.md", read_text_retry(home / "rules.md").strip()))
    if repo_info:
        parts.append((f"repo_commit ({repo_info['commit_sha'][:12]})", repo_info["meta_text"].strip()))
        if repo_info.get("diff_text", "").strip():
            parts.append((f"commit_diff ({repo_info['commit_sha'][:12]})", repo_info["diff_text"].strip()))
    if diff_text.strip():
        parts.append(("diff", diff_text.strip()))

    max_chars = budget * 4
    full_blocks = [f"=== {n} ===\n{t}\n" for n, t in parts]
    full_pack = "\n".join(full_blocks)
    if len(full_pack) <= max_chars:
        return full_pack, estimate_tokens(full_pack)

    min_content_chars = 12
    min_b_lens = []
    for idx, (name, text) in enumerate(parts):
        trim_hdr = f"=== {name} (trimmed to fit {budget} tokens) ===\n"
        min_b_lens.append(min(len(full_blocks[idx]), len(trim_hdr) + min(len(text), min_content_chars) + 1))
    min_total_chars = sum(min_b_lens) + max(0, len(parts) - 1)
    min_required_tokens = max(80 if (repo_info or has_diff) else 1, estimate_tokens("x" * min_total_chars))
    if (repo_info or has_diff) and budget < min_required_tokens:
        raise ValueError(
            f"Review budget ({budget} tokens) is too small to include repository metadata and commit diff "
            f"(minimum {min_required_tokens} tokens)."
        )

    blocks, used_chars = [], 0
    total_parts = len(parts)
    for idx, (name, text) in enumerate(parts):
        sep_chars = 1 if idx < total_parts - 1 else 0
        strict_min_rem = sum(min_b_lens[r] for r in range(idx + 1, total_parts)) + max(0, total_parts - 1 - idx)
        desired_rem = 0
        for r in range(idx + 1, total_parts):
            rname = parts[r][0]
            share = max_chars // 3 if ("diff" in rname or "repo_commit" in rname) else max_chars // (total_parts + 1)
            desired_rem += min(len(full_blocks[r]), max(min_b_lens[r], share))
        desired_rem += max(0, total_parts - 1 - idx)

        max_avail = max(min_b_lens[idx], max_chars - used_chars - sep_chars - strict_min_rem)
        target_avail = max(min_b_lens[idx], max_chars - used_chars - sep_chars - desired_rem)
        avail_chars = min(max_avail, target_avail)

        if len(full_blocks[idx]) <= avail_chars:
            b = full_blocks[idx]
        else:
            header = f"=== {name} (trimmed to fit {budget} tokens) ===\n"
            room = max(1, avail_chars - len(header) - 1)
            b = f"{header}{text[:room]}\n"
        blocks.append(b)
        used_chars += len(b) + sep_chars

    pack = "\n".join(blocks)
    if len(pack) > max_chars:
        pack = pack[:max_chars]
    return pack, estimate_tokens(pack)
