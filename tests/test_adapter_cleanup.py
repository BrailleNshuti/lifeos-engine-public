"""A model CLI that leaves a process in its working directory must not cost us the answer it already gave."""
import sys

import pytest

from lifeos import ask

# The "CLI": leaves a short-lived child behind that holds a file open in its working directory (as a background helper of a
# real CLI can), waits until that is true, then prints its answer. On Windows the directory cannot be removed meanwhile.
FAKE_CLI = (
    "import os, subprocess, sys, time\n"
    "D = subprocess.DEVNULL\n"  # detached from our pipes, so the caller does not wait for it
    "subprocess.Popen([sys.executable, '-c', \"import time; f = open('held.txt', 'w'); time.sleep(4)\"], cwd=os.getcwd(),\n"
    "                 stdin=D, stdout=D, stderr=D)\n"
    "while not os.path.exists('held.txt'):\n"
    "    time.sleep(0.01)\n"
    "time.sleep(0.2)\n"
    "print('the answer')\n"
)


def test_a_working_directory_that_cannot_be_removed_yet_does_not_lose_the_answer(monkeypatch):
    monkeypatch.setattr(ask.shutil, "which", lambda name: sys.executable)
    monkeypatch.setattr(ask, "current_review_cwd", lambda: None)
    assert ask._run_cli(["python", "-c", FAKE_CLI], "", via_stdin=False) == "the answer"


def test_a_cli_that_fails_still_fails_with_its_own_message(monkeypatch):
    monkeypatch.setattr(ask.shutil, "which", lambda name: sys.executable)
    monkeypatch.setattr(ask, "current_review_cwd", lambda: None)
    with pytest.raises(ask.AskError, match="failed"):
        ask._run_cli(["python", "-c", "import sys; sys.stderr.write('nope'); sys.exit(3)"], "", via_stdin=False)


def test_a_missing_cli_is_still_reported_as_missing(monkeypatch):
    monkeypatch.setattr(ask.shutil, "which", lambda name: None)
    with pytest.raises(ask.ToolMissing):
        ask._run_cli(["no-such-tool"], "", via_stdin=False)
