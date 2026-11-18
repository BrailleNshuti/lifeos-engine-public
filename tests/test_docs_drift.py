"""Docs may not drift from the code: every command is in the README table, and every command answers --help."""
import re
from pathlib import Path

import pytest

from lifeos.cli import build_parser

ROOT = Path(__file__).resolve().parent.parent


def commands():
    parser = build_parser()
    action = next(a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction")
    return sorted(action.choices)


def test_every_command_has_a_readme_row():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    missing = [c for c in commands() if not re.search(rf"`lifeos {re.escape(c)}[ `]", readme)]
    assert not missing, f"README.md has no row for: {missing}"


@pytest.mark.parametrize("cmd", commands())
def test_help_works_for_every_command(cmd, capsys):
    from lifeos.cli import main
    with pytest.raises(SystemExit) as exit_:
        main([cmd, "--help"])
    assert exit_.value.code == 0
    assert "usage" in capsys.readouterr().out.lower()
