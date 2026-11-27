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


def test_block_pauses_a_task_with_a_dated_reason(home):
    path = taskclose.block(home, "T-261128", "the project is paused by the owner", today=D)
    text = path.read_text(encoding="utf-8")
    assert "status: blocked" in text and "## Update 2026-11-28\nBlocked on purpose: the project is paused by the owner" in text


def test_block_refuses_a_done_task_an_empty_reason_and_a_secret(home):
    with pytest.raises(taskclose.CloseError, match="why"):
        taskclose.block(home, "T-261128", "  ")
    with pytest.raises(taskclose.CloseError, match="private data"):
        taskclose.block(home, "T-261128", "key " + "sk" + "-" + "abcDEF1234567890abcdEFGH12")
    taskclose.close(home, "T-261128", "tests/test_x.py", today=D)
    with pytest.raises(taskclose.CloseError, match="already done"):
        taskclose.block(home, "T-261128", "too late")


def test_block_command(home, capsys):
    assert main(["--home", str(home), "task", "block", "T-261128", "--reason", "waiting for the RAM"]) == 0
    assert "blocked: tasks" in capsys.readouterr().out


# Found by a blind review (Gemini, 2026-11-27) and confirmed by hand against the code.
def test_a_proof_heading_at_the_end_of_the_file_still_gets_the_proof(home):
    path = home / "tasks" / "T-261128-demo.md"
    path.write_text(TASK.split("## Proof")[0] + "## Proof", encoding="utf-8")
    taskclose.close(home, "T-261128", "tests/test_x.py", today=D)
    text = path.read_text(encoding="utf-8")
    assert "status: done" in text and "tests/test_x.py" in text and lint.check(home) == []


def test_a_decorated_proof_heading_is_used_and_the_result_is_not_lost(home):
    path = home / "tasks" / "T-261128-demo.md"
    path.write_text(TASK.replace("## Proof\n", "## Proof (links)\n"), encoding="utf-8")
    taskclose.close(home, "T-261128", "tests/test_x.py", result="It works.", today=D)
    text = path.read_text(encoding="utf-8")
    assert "## Proof (links)\ntests/test_x.py" in text and "It works." in text and "status: done" in text


def test_nothing_is_written_when_the_proof_cannot_be_placed(home, monkeypatch):
    path = home / "tasks" / "T-261128-demo.md"
    before = path.read_bytes()
    monkeypatch.setattr(taskclose, "_place", lambda *a, **k: None)
    with pytest.raises(taskclose.CloseError, match="place"):
        taskclose.close(home, "T-261128", "tests/test_x.py", today=D)
    assert path.read_bytes() == before


def test_status_and_done_when_lines_in_the_body_are_not_the_front_matter(home):
    path = home / "tasks" / "T-261128-demo.md"
    body_only = "---\nid: T-261128-demo\ngoal: g\n---\nstatus: doing\ndone_when: TODO\n## Proof\n"
    path.write_text(body_only, encoding="utf-8")
    with pytest.raises(taskclose.CloseError, match="status"):
        taskclose.close(home, "T-261128", "tests/test_x.py", today=D)
    assert path.read_text(encoding="utf-8") == body_only
    ok = TASK.replace("## Task\n", "## Task\ndone_when: TODO (a quoted template line)\nstatus: doing\n")
    path.write_text(ok, encoding="utf-8")
    taskclose.close(home, "T-261128", "tests/test_x.py", today=D)
    text = path.read_text(encoding="utf-8")
    assert text.split("---\n")[1].count("status: done") == 1 and "status: doing" in text.split("---\n", 2)[2]


def test_a_front_matter_that_never_closes_is_refused(home):
    (home / "tasks" / "T-261128-demo.md").write_text("---\nid: x\nstatus: doing\n## Proof\n", encoding="utf-8")
    with pytest.raises(taskclose.CloseError, match="front matter"):
        taskclose.close(home, "T-261128", "tests/test_x.py", today=D)
    with pytest.raises(taskclose.CloseError, match="front matter"):
        taskclose.block(home, "T-261128", "paused")
