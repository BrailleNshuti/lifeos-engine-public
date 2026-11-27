"""A task id can never point outside the home folder: traversal, absolute paths and drive letters are refused."""
import shutil

import pytest

from lifeos.cli import main
from lifeos.context import task_file


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    (tmp_path / "outside.md").write_text("---\nid: outside\n---\n", encoding="utf-8")
    return target


@pytest.mark.parametrize("bad", ["../outside", ".." + chr(92) + "outside", "T-261116/../../outside", "/etc/passwd",
                                 "C:" + chr(92) + "Windows" + chr(92) + "win.ini", "", ".", "..", "T-261116\x00evil"])
def test_a_path_like_task_id_is_refused(home, bad):
    with pytest.raises(ValueError):
        task_file(home, bad)


def test_a_prefix_still_finds_the_task_inside_the_home(home):
    found = task_file(home, "T-2611")
    assert found.parent == home / "tasks"


@pytest.mark.parametrize("command", [["context", "../outside"], ["ask", "claude", "../outside", "--dry-run"],
                                     ["delegate", "../outside", "--dry-run"], ["rate", "../outside", "claude", "3"]])
def test_commands_refuse_a_path_like_task_id_without_touching_the_outside_file(home, tmp_path, command, capsys):
    before = (tmp_path / "outside.md").read_text(encoding="utf-8")
    try:
        code = main(["--home", str(home), *command])
    except ValueError:
        code = 2
    assert code != 0
    assert (tmp_path / "outside.md").read_text(encoding="utf-8") == before
