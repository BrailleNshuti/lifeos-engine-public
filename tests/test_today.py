import datetime as dt

from lifeos import decision, experiment, today
from lifeos.cli import main

D = dt.date(2026, 11, 18)


def task(home, name, status, due, goal="Do it"):
    (home / "tasks").mkdir(exist_ok=True)
    (home / "tasks" / f"{name}.md").write_text(
        f"---\nid: {name}\ngoal: {goal}\nstatus: {status}\ndue: {due}\n---\n", encoding="utf-8")


def test_the_view_names_the_next_task_and_everything_waiting(tmp_path):
    task(tmp_path, "T-261101-late", "doing", "2026-11-10", "Late one")
    task(tmp_path, "T-261102-soon", "todo", "2026-11-20", "Soon one")
    task(tmp_path, "T-261103-done", "done", "2026-11-01")
    decision.record(tmp_path, "Old call", "why", revisit="2026-11-01", today=D)
    view = today.build(tmp_path, today=D)
    assert view["next_task"]["id"] == "T-261101-late" and view["overdue"] == 1
    assert [t["id"] for t in view["open_tasks"]] == ["T-261101-late", "T-261102-soon"]
    assert view["decisions_due"] == 1 and "Late one" in today.render(view)


def test_an_empty_home_still_gives_a_calm_view(tmp_path):
    view = today.build(tmp_path, today=D)
    assert view["next_task"] is None
    assert "Nothing open" in today.render(view)


def test_running_experiment_is_shown(tmp_path):
    experiment.start(tmp_path, "Hardest task first", "minutes_saved", days=14, today=D)
    assert "E-001" in today.render(today.build(tmp_path, today=D))


def test_cli(tmp_path, capsys):
    (tmp_path / "now.md").write_text("# now\n", encoding="utf-8")
    task(tmp_path, "T-261101-x", "doing", "2099-01-01", "Ship it")
    assert main(["--home", str(tmp_path), "today"]) == 0
    assert "Ship it" in capsys.readouterr().out
