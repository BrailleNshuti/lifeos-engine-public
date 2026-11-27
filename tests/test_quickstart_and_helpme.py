"""The README's first screen runs, and `help-me` names the newest daily commands (round 5 items 12 and 18)."""
import re
from pathlib import Path

import pytest

from lifeos.cli import build_parser, main
from lifeos.cmds_misc import HELP_ME

ROOT = Path(__file__).resolve().parents[1]
FIRST_SCREEN = (ROOT / "README.md").read_text(encoding="utf-8").split("## What it does")[0]


def commands_in(text):
    return re.findall(r"`lifeos ([a-z][a-z-]*)", text)


def test_the_first_screen_names_commands_that_exist():
    from lifeos.cli import build_parser
    import argparse
    names = next(a for a in build_parser()._actions if isinstance(a, argparse._SubParsersAction)).choices
    found = commands_in(FIRST_SCREEN)
    assert found, "the quickstart should name commands"
    assert [c for c in found if c not in names] == []


def test_the_quickstart_commands_that_are_safe_to_run_do_run(tmp_path, demo, monkeypatch, capsys):
    import shutil
    home = tmp_path / "home"
    shutil.copytree(demo, home)
    monkeypatch.setenv("LIFEOS_HOME", str(home))
    monkeypatch.chdir(home)
    assert main(["demo"]) == 0
    assert main(["canary"]) == 0
    assert main(["numbers", "--html", str(tmp_path / "numbers.html")]) == 0
    assert (tmp_path / "numbers.html").exists()


def test_help_me_names_the_newest_daily_commands_and_they_exist():
    import argparse
    names = next(a for a in build_parser()._actions if isinstance(a, argparse._SubParsersAction)).choices
    for word in ("lifeos next", "lifeos task close", "lifeos waiting"):
        assert word in HELP_ME
    assert [c for c in commands_in(HELP_ME.replace("lifeos ", "`lifeos ")) if c not in names] == []
