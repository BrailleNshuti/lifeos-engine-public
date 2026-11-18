import datetime as dt

from lifeos import decision, stale
from lifeos.cli import main

D = dt.date(2026, 11, 18)


def task(home, name, status):
    (home / "tasks").mkdir(exist_ok=True)
    (home / "tasks" / f"{name}.md").write_text(f"---\nid: {name}\ngoal: g\nstatus: {status}\n---\n", encoding="utf-8")


def pred(home, rows):
    (home / "logs").mkdir(exist_ok=True)
    (home / "logs" / "predictions.csv").write_text("date,id,kind,value,text\n" + "".join(r + "\n" for r in rows), encoding="utf-8")


def test_old_open_tasks_unresolved_predictions_and_due_decisions_are_listed(tmp_path):
    task(tmp_path, "T-261001-old", "doing")
    task(tmp_path, "T-261115-new", "doing")
    task(tmp_path, "T-260901-finished", "done")
    pred(tmp_path, ["2026-09-01,P-001,predict,70,old claim", "2026-11-10,P-002,predict,60,new claim",
                    "2026-08-01,P-003,predict,50,done claim", "2026-08-20,P-003,resolve,1,"])
    decision.record(tmp_path, "Old call", "why", revisit="2026-11-01", today=D)
    out = stale.find(tmp_path, today=D, days=14)
    assert [t["id"] for t in out["tasks"]] == ["T-261001-old"] and out["tasks"][0]["age"] == 48
    assert [p["id"] for p in out["predictions"]] == ["P-001"]
    assert len(out["decisions"]) == 1 and out["total"] == 3


def test_nothing_stale_says_so(tmp_path):
    out = stale.find(tmp_path, today=D)
    assert out["total"] == 0 and "Nothing stale" in stale.render(out)


def test_cli_exit_code_is_zero_even_with_findings(tmp_path, capsys):
    (tmp_path / "now.md").write_text("# now\n", encoding="utf-8")
    task(tmp_path, "T-260101-old", "todo")
    assert main(["--home", str(tmp_path), "stale", "--days", "10"]) == 0
    assert "T-260101-old" in capsys.readouterr().out
