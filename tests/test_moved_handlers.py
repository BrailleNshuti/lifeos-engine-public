"""T8: each handler moved to lifeos/cmds_misc.py works through main([...]) on the made-up demo home (exit codes and one line of output)."""
import shutil

import pytest

from lifeos import cli, cmds_misc
from lifeos.cli import main

IBAN = "DE89 3704 " + "0044 0532 0130 00"  # built at run time so this file never trips the guard


@pytest.fixture
def home(tmp_path, demo, monkeypatch):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    monkeypatch.setenv("LIFEOS_HOME", str(target))
    return target


def test_cli_still_exposes_every_moved_handler():
    for name in ("cmd_study", "cmd_lab", "cmd_doctor", "cmd_vocab", "cmd_guard", "cmd_sort_csv"):
        assert getattr(cli, name) is getattr(cmds_misc, name)


def test_doctor_reports_the_home(home, capsys):
    assert main(["doctor"]) == 0
    assert "LifeOS home" in capsys.readouterr().out


def test_study_sources_lists_without_error(home):
    assert main(["study", "sources"]) == 0


def test_lab_without_arguments_is_a_usage_error(home, capsys):
    with pytest.raises(SystemExit) as stop:
        main(["lab"])
    assert stop.value.code == 2
    assert "usage" in capsys.readouterr().err.lower()


def test_sort_csv_with_a_missing_file_exits_2_with_a_message(home, capsys, tmp_path):
    assert main(["sort-csv", str(tmp_path / "nope.csv")]) == 2
    assert "nope.csv" in capsys.readouterr().err


def test_vocab_quiz_on_an_empty_list_says_nothing_is_due(home, capsys):
    assert main(["vocab", "quiz"]) == 0
    assert "Nothing due" in capsys.readouterr().out


def test_guard_passes_a_clean_file_and_stops_a_leak(home, tmp_path, capsys):
    clean = tmp_path / "clean.md"
    clean.write_text("ordinary planning text\n", encoding="utf-8")
    leak = tmp_path / "leak.md"
    leak.write_text(f"pay to {IBAN}\n", encoding="utf-8")
    assert main(["guard", str(clean)]) == 0
    capsys.readouterr()
    assert main(["guard", str(leak)]) == 1
    seen = capsys.readouterr()
    assert "IBAN" in seen.out + seen.err
    assert IBAN not in seen.out + seen.err  # the finding is masked, never printed whole
