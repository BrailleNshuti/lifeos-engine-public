"""`lifeos task close`: finish a task with a real proof, in one atomic write (round 5). Made-up data only."""
import datetime as dt

import pytest

from lifeos import lint, taskclose
from lifeos.cli import main

D = dt.date(2026, 11, 28)
TASK = """---
id: T-261128-demo
goal: a made-up goal
done_when: a made-up finish line that can be checked
route: claude
level: L0
status: doing
due: 2026-12-05
---
## Context

## Task
a made-up goal

## Result (written back here)

## Proof

## Ledger: minutes spent __
"""


@pytest.fixture
def home(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "now.md").write_text("# now", encoding="utf-8")
    (tmp_path / "tasks" / "T-261128-demo.md").write_text(TASK, encoding="utf-8")
    return tmp_path


def test_close_sets_done_writes_the_proof_and_lint_is_happy(home):
    path = taskclose.close(home, "T-261128", "pull request #131 and tests/test_backup.py", today=D)
    text = path.read_text(encoding="utf-8")
    assert "status: done" in text and "## Proof\npull request #131" in text
    assert lint.check(home) == []


def test_a_result_goes_above_the_proof(home):
    path = taskclose.close(home, "T-261128-demo", "https://example.org/page 2026", result="It works.", today=D)
    text = path.read_text(encoding="utf-8")
    assert text.index("## Result · you · 2026-11-28\nIt works.") < text.index("## Proof")


def test_no_checkable_proof_means_nothing_is_written(home):
    before = (home / "tasks" / "T-261128-demo.md").read_bytes()
    with pytest.raises(taskclose.CloseError, match="checkable"):
        taskclose.close(home, "T-261128", "I checked it, trust me", today=D)
    assert (home / "tasks" / "T-261128-demo.md").read_bytes() == before


def test_a_todo_finish_line_and_a_done_task_are_refused(home):
    path = home / "tasks" / "T-261128-demo.md"
    path.write_text(TASK.replace("a made-up finish line that can be checked", "TODO (you write this line)"), encoding="utf-8")
    with pytest.raises(taskclose.CloseError, match="TODO"):
        taskclose.close(home, "T-261128", "tests/test_x.py", today=D)
    path.write_text(TASK, encoding="utf-8")
    taskclose.close(home, "T-261128", "tests/test_x.py", today=D)
    with pytest.raises(taskclose.CloseError, match="already done"):
        taskclose.close(home, "T-261128", "tests/test_x.py", today=D)


def test_a_secret_in_the_proof_or_result_is_refused(home):
    fake = "sk" + "-" + "abcDEF1234567890abcdEFGH12"
    for kwargs in ({"proof": f"tests/a.py {fake}"}, {"proof": "tests/a.py", "result": f"key {fake}"}):
        with pytest.raises(taskclose.CloseError, match="private data"):
            taskclose.close(home, "T-261128", today=D, **kwargs)


def test_crlf_files_keep_their_line_endings(home):
    path = home / "tasks" / "T-261128-demo.md"
    path.write_bytes(TASK.replace("\n", "\r\n").encode("utf-8"))
    taskclose.close(home, "T-261128", "tests/test_x.py", today=D)
    raw = path.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")


def test_unknown_or_ambiguous_ids_give_a_clear_error(home):
    with pytest.raises(taskclose.CloseError):
        taskclose.close(home, "T-999999", "tests/a.py")
    with pytest.raises(taskclose.CloseError):
        taskclose.close(home, "nonsense", "tests/a.py")


def test_the_command_closes_and_reports(home, capsys):
    assert main(["--home", str(home), "task", "close", "T-261128", "--proof", "tests/test_x.py"]) == 0
    assert "closed: tasks" in capsys.readouterr().out
    assert main(["--home", str(home), "task", "close", "T-261128", "--proof", "tests/test_x.py"]) == 2
