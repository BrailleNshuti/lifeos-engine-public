"""T16b: STATE.md only names things that exist: pull requests that are merged on this repo's own history, files and commands."""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATE = (ROOT / "STATE.md").read_text(encoding="utf-8")


def test_every_file_path_in_backticks_exists():
    missing = []
    for path in set(re.findall(r"`((?:docs|lifeos|tests|scripts|examples)/[A-Za-z0-9_./-]+\.[a-z]+)`", STATE)):
        if not (ROOT / path).exists():
            missing.append(path)
    assert not missing, f"STATE.md names files that do not exist: {missing}"


def test_every_pull_request_number_it_names_was_merged_into_this_history():
    numbers = {int(n) for n in re.findall(r"\bPRs? (\d{2,3})\b", STATE)}
    if not numbers:
        pytest.skip("STATE.md names no pull request")
    log = subprocess.run(["git", "log", "--merges", "--format=%s"], cwd=ROOT, capture_output=True, text=True)
    if log.returncode != 0 or not log.stdout:
        pytest.skip("no git history here (shallow or no repository)")
    merged = {int(n) for n in re.findall(r"Merge pull request #(\d+)", log.stdout)}
    if len(merged) < 20:
        pytest.skip("shallow history: too few merge commits to judge")
    missing = sorted(n for n in numbers if n not in merged)
    assert not missing, f"STATE.md names pull requests that are not merged here: {missing}"
