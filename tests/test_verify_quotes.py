"""`lifeos verify-quotes TASK`: the quote check on its own, for an answer already in a task file. No model call."""
import shutil

import pytest

from lifeos import check
from lifeos.cli import main

LINE = "hat sich innerhalb von zwei Wochen nach dem Einzug anzumelden"
MISSING = "a fine of fifty thousand euros applies to every single case"


def test_quote_report_splits_found_and_missing():
    source = "padding " * 10 + LINE
    text = f'It says "{LINE}" and "{MISSING}".'
    found, missing = check.quote_report(text, source)
    assert found == [LINE] and missing == [MISSING]


def test_quote_report_ignores_case_and_spacing():
    found, missing = check.quote_report('"HAT SICH  innerhalb von zwei Wochen nach dem Einzug anzumelden"', LINE)
    assert len(found) == 1 and missing == []


def test_quote_report_with_no_quotes_is_empty():
    assert check.quote_report("no quotes here at all", LINE) == ([], [])


@pytest.fixture
def home(tmp_path, demo, monkeypatch):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    monkeypatch.setenv("LIFEOS_HOME", str(target))
    return target


def put_answer(home, answer, context=LINE):
    task = home / "tasks" / "T-261116-demo-cli.md"
    raw = task.read_text(encoding="utf-8").split("\n## Result", 1)[0]
    raw = raw.replace("## Context (links, not essays)\n", f"## Context (links, not essays)\n{context}\n", 1)
    task.write_text(raw + f"\n## Result · fake · 2026-11-27\n{answer}\n", encoding="utf-8")


def test_the_command_reports_real_over_total_and_the_missing_line(home, capsys):
    put_answer(home, f'It says "{LINE}" and also "{MISSING}". Next step: none.')
    assert main(["verify-quotes", "T-261116"]) == 1  # a missing quote is a non-zero exit
    out = capsys.readouterr().out
    assert "1 of 2" in out and MISSING[:30] in out


def test_the_command_exits_0_when_every_quote_is_there(home, capsys):
    put_answer(home, f'It says "{LINE}". Next step: none.')
    assert main(["verify-quotes", "T-261116"]) == 0
    assert "1 of 1" in capsys.readouterr().out


def test_the_command_says_so_when_there_is_nothing_to_check(home, capsys):
    put_answer(home, "No quotes here. Next step: none.")
    assert main(["verify-quotes", "T-261116"]) == 0
    assert "no quoted lines" in capsys.readouterr().out.lower()


def test_the_command_warns_when_the_context_is_short(home, capsys):
    put_answer(home, f'It says "{LINE}". Next step: none.')
    main(["verify-quotes", "T-261116"])
    assert "short" in capsys.readouterr().out.lower()


def test_an_unknown_task_is_a_clean_error(home, capsys):
    assert main(["verify-quotes", "T-999999"]) == 2
    assert capsys.readouterr().err
