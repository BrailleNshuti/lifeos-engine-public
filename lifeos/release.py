"""`lifeos release [--repo PATH]`: read-only release plan from CHANGELOG `[Unreleased]`. It never edits, tags or pushes.

It checks that pyproject.toml and `__version__` agree, counts the unreleased entries, proposes a bump (a new command or
feature means minor, only fixes means patch) and prints draft notes. The version number and the tag are the owner's
decision (rule 8); this only prepares the facts.
"""
import re
from pathlib import Path


def _version(text, pattern):
    m = re.search(pattern, text)
    return m.group(1) if m else None


def plan(repo):
    repo = Path(repo)
    problems = []
    pyproject = (repo / "pyproject.toml").read_text(encoding="utf-8")
    init = (repo / "lifeos" / "__init__.py").read_text(encoding="utf-8")
    a = _version(pyproject, r'(?m)^version\s*=\s*"([^"]+)"')
    b = _version(init, r'__version__\s*=\s*"([^"]+)"')
    if a != b:
        problems.append(f"Versions differ: pyproject.toml {a}, __init__.py {b}.")
    log = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(r"## \[Unreleased\]\n(.*?)(?=\n## \[|\Z)", log, re.S)
    entries = [ln for ln in (m.group(1) if m else "").splitlines() if ln.startswith("- ")]
    if not entries:
        problems.append("Nothing under [Unreleased]: there is nothing to release.")
    major, minor, patch = (int(x) for x in (a or "0.0.0").split("."))
    feature = any(re.match(r"- `lifeos [a-z-]+", e) or "new" in e.lower() for e in entries)
    proposed = f"{major}.{minor + 1}.0" if feature else f"{major}.{minor}.{patch + 1}"
    notes = f"## [{proposed}]\n\n" + "\n".join(entries) + "\n"
    return {"current": a, "proposed": proposed, "entries": len(entries), "problems": problems, "notes": notes}


def render(p):
    lines = [f"Current {p['current']}, proposed {p['proposed']} ({p['entries']} unreleased entries).", ""]
    lines += [f"PROBLEM: {x}" for x in p["problems"]] + ([""] if p["problems"] else [])
    lines += ["Draft notes:", p["notes"],
              "You decide the number and the tag. Nothing was changed. After you bump both version files and move the "
              "notes under the new heading: pytest, guard, then tag."]
    return "\n".join(lines)
