import datetime as dt

import pytest

from lifeos import calibrate, decision
from lifeos.cli import main

D = dt.date(2026, 11, 18)


def test_record_writes_a_dated_file_and_a_linked_prediction(tmp_path):
    path = decision.record(tmp_path, "Use Sonnet by default", "cheaper and enough", revisit="2026-12-18",
                           predict="Sonnet is enough for 90 % of tasks", percent=80, today=D)
    text = path.read_text(encoding="utf-8")
    assert path.name == "D-261118-use-sonnet-default.md"
    assert "revisit: 2026-12-18" in text and "prediction: P-001" in text and "cheaper and enough" in text
    assert calibrate.report(tmp_path)["open"] == 1


def test_never_overwrites_and_refuses_private_text(tmp_path):
    a = decision.record(tmp_path, "Same title", "why", today=D)
    b = decision.record(tmp_path, "Same title", "why", today=D)
    assert a != b
    with pytest.raises(decision.DecisionError, match="private"):
        decision.record(tmp_path, "t", "key sk-ant-api03-" + "a1B2c3D4" * 5, today=D)
    with pytest.raises(decision.DecisionError):
        decision.record(tmp_path, "", "why", today=D)
    with pytest.raises(decision.DecisionError, match="revisit"):
        decision.record(tmp_path, "t", "why", revisit="soon", today=D)


def test_due_lists_decisions_whose_revisit_date_has_come(tmp_path):
    decision.record(tmp_path, "Old call", "why", revisit="2026-11-01", today=D)
    decision.record(tmp_path, "Later call", "why", revisit="2027-01-01", today=D)
    decision.record(tmp_path, "No date", "why", today=D)
    due = decision.due(tmp_path, today=D)
    assert [d["title"] for d in due] == ["Old call"]
    assert len(decision.list_all(tmp_path)) == 3


def test_cli(tmp_path, capsys):
    (tmp_path / "now.md").write_text("# now\n", encoding="utf-8")
    h = ["--home", str(tmp_path)]
    assert main(h + ["decide", "add", "Pick Sonnet", "--why", "cheap", "--revisit", "2020-01-01"]) == 0
    assert main(h + ["decide", "list"]) == 0
    assert "Pick Sonnet" in capsys.readouterr().out
    assert main(h + ["decide", "due"]) == 0
    assert "Pick Sonnet" in capsys.readouterr().out
    assert main(h + ["decide", "add", "x", "--why", ""]) == 2
