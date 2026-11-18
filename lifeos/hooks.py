"""Install the pre-commit hook that runs the privacy guard on what is about to be committed."""
from pathlib import Path

SCRIPT = "#!/bin/sh\n# installed by `lifeos hook install`\nexec lifeos guard --staged\n"


class HookError(Exception):
    pass


def install(repo=".", force=False):
    git_dir = Path(repo) / ".git"
    if not git_dir.is_dir():
        raise HookError("Not a git repository (no .git folder here).")
    path = git_dir / "hooks" / "pre-commit"
    if path.exists() and path.read_text(encoding="utf-8", errors="replace") != SCRIPT and not force:
        raise HookError("A different pre-commit hook already exists. Use --force to replace it.")
    path.parent.mkdir(exist_ok=True)
    path.write_text(SCRIPT, encoding="utf-8", newline="\n")
    path.chmod(0o755)
    return path
