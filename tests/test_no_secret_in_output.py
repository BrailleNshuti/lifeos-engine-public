"""No command prints a full secret, even when the task file holds one: the guard stops the call and shows a masked excerpt."""
import shutil

import pytest

from lifeos import ask
from lifeos.cli import main

KEY = "ghp_" + "a1B2" * 9  # assembled at run time, never a real token
IBAN = "DE89 3704 " + "0044 0532 0130 00"


@pytest.fixture
def home(tmp_path, demo, monkeypatch):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    task = target / "tasks" / "T-261116-demo-cli.md"
    raw = task.read_text(encoding="utf-8")
    task.write_text(raw.replace("## Context (links, not essays)\n",
                                f"## Context (links, not essays)\nnote with a secret {KEY} and an account {IBAN}\n", 1),
                    encoding="utf-8")
    monkeypatch.setenv("LIFEOS_HOME", str(target))
    monkeypatch.setitem(ask.ADAPTERS, "claude", lambda prompt: pytest.fail("a model was called with a secret"))
    return target


@pytest.mark.parametrize("command", [
    ["ask", "claude", "T-261116"],
    ["ask", "claude", "T-261116", "--dry-run"],
    ["delegate", "T-261116"],
    ["delegate", "T-261116", "--dry-run"],
    ["guard", "tasks/T-261116-demo-cli.md"],
])
def test_a_secret_in_a_task_is_never_printed_whole_and_never_sent(home, command, capsys, monkeypatch):
    monkeypatch.chdir(home)
    try:
        main(command)
    except SystemExit:
        pass
    seen = capsys.readouterr()
    shown = seen.out + seen.err
    assert KEY not in shown and IBAN not in shown and IBAN.replace(" ", "") not in shown
