"""The README may not name a command that does not exist, and every command has a help line (documentation cannot lie)."""
import re
from pathlib import Path

import pytest

from lifeos.cli import build_parser

ROOT = Path(__file__).resolve().parents[1]


def _commands():
    parser = build_parser()
    for action in parser._actions:
        choices = getattr(action, "choices", None)
        if choices and "task" in choices:
            return choices
    raise AssertionError("no sub-commands found")


def _readme_commands():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    found = set()
    for cell in re.findall(r"`lifeos ([a-z][a-z-]*)", text):
        found.add(cell)
    return found


def test_every_command_the_readme_names_exists():
    commands = _commands()
    missing = sorted(name for name in _readme_commands() if name not in commands)
    assert not missing, f"README names commands that do not exist: {missing}"


def test_the_readme_names_a_good_share_of_the_commands():
    """A guard against the regex silently matching nothing."""
    assert len(_readme_commands()) >= 40


@pytest.mark.parametrize("name", sorted(_commands()))
def test_every_command_has_a_help_line(name):
    parser = build_parser()
    for action in parser._actions:
        choices = getattr(action, "choices", None)
        if choices and name in choices:
            helps = {a.dest: a.help for a in getattr(action, "_choices_actions", [])}
            assert helps.get(name), f"`lifeos {name}` has no help line"
            return
    raise AssertionError(name)


# Commands named in the handoff backlog that are planned and do not exist yet. Remove a name here when its feature merges:
# the second test fails if a planned command already exists, so this list cannot go stale.
PLANNED = {"help-me"}  # planned in docs/HANDOFF.md section 9, item 25
DOC_FILES = sorted(list((ROOT / "docs").glob("*.md")) + [ROOT / "STATE.md", ROOT / "CHANGELOG.md", ROOT / "AGENTS.md"])


def test_every_command_named_in_any_doc_exists():
    commands = _commands()
    missing = {}
    for path in DOC_FILES:
        for name in set(re.findall(r"`lifeos ([a-z][a-z-]*)", path.read_text(encoding="utf-8"))):
            if name not in commands and name not in PLANNED:
                missing.setdefault(path.name, set()).add(name)
    assert not missing, f"docs name commands that do not exist: {missing}"


def test_planned_commands_do_not_exist_yet():
    assert not (PLANNED & set(_commands())), "a planned command now exists: remove it from PLANNED"
