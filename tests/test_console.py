"""Output must never crash the command: a character the console cannot show becomes '?', the exit code is unchanged."""
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

from lifeos import console

ROOT = Path(__file__).resolve().parent.parent


def test_a_console_that_cannot_encode_a_character_gets_a_question_mark(monkeypatch):
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", stream)
    console.tolerate_encoding()
    print("limit ≤ 24 and café")
    stream.flush()
    assert raw.getvalue().startswith(b"limit ? 24 and caf\xe9")


def test_streams_that_cannot_be_reconfigured_are_left_alone(monkeypatch):
    class Plain:
        def write(self, s):
            return len(s)

    monkeypatch.setattr(sys, "stdout", Plain())
    monkeypatch.setattr(sys, "stderr", Plain())
    console.tolerate_encoding()  # no exception


def test_the_real_command_does_not_crash_when_its_output_is_cp1252(tmp_path, demo):
    home = tmp_path / "home"
    shutil.copytree(demo, home)
    task = next((home / "tasks").glob("T-261116*.md"))
    task.write_text(task.read_text(encoding="utf-8") + "\nThe limit is ≤ 24 calls and the sign is →.\n", encoding="utf-8")
    env = dict(os.environ, PYTHONIOENCODING="cp1252")
    run = subprocess.run([sys.executable, "-m", "lifeos.cli", "--home", str(home), "context", "T-261116", "--budget", "4000"],
                         cwd=ROOT, env=env, capture_output=True)
    assert run.returncode == 0, run.stderr.decode("cp1252", "replace")[-400:]
    assert b"UnicodeEncodeError" not in run.stderr
    assert b"The limit is ? 24 calls and the sign is ?." in run.stdout
