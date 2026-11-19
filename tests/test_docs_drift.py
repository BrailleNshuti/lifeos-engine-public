"""Docs may not drift from the code: every command is in the README table, and every command answers --help."""
import argparse
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


def test_top_level_help_works(capsys):
    """The front door: `lifeos --help` renders every command's one-line help (a bare % once crashed it)."""
    from lifeos.cli import main
    with pytest.raises(SystemExit) as exit_:
        main(["--help"])
    assert exit_.value.code == 0
    out = capsys.readouterr().out
    assert "usage" in out.lower()
    listed = re.search(r"\{([^}]*)\}", out)
    assert listed, "top-level help lists no command choices"
    assert sorted(listed.group(1).split(",")) == commands()


def _all_parsers(parser):
    yield parser
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for child in action.choices.values():
                yield from _all_parsers(child)


def test_every_parser_formats_its_help_text():
    """Every parser at every depth must render its own help; catches unescaped % in any help string."""
    for parser in _all_parsers(build_parser()):
        parser.format_help()


@pytest.mark.parametrize("cmd", commands())
def test_help_works_for_every_command(cmd, capsys):
    from lifeos.cli import main
    with pytest.raises(SystemExit) as exit_:
        main([cmd, "--help"])
    assert exit_.value.code == 0
    assert "usage" in capsys.readouterr().out.lower()
