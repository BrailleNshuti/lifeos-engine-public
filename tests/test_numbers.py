import datetime as dt
import shutil

import pytest

from lifeos import calibrate, numbers, vocab
from lifeos.cli import main

D = dt.date(2026, 11, 24)


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def test_numbers_counts_the_engine_and_the_home(home):
    calibrate.predict(home, "it works", 70, today=D)
    vocab.add(home, "das Haus", "the house", today=D)
    d = numbers.build(home, commands=30)
    assert d["commands"] == 30 and d["modules"] >= 20 and d["code_lines"] > 1000
    assert d["guard"]["blocked"] == d["guard"]["total"] > 100
    assert d["ledger"]["ok"] is True
    assert d["practice"]["predictions"] == 1 and d["practice"]["vocab_words"] == 1


def test_page_has_no_task_ids_paths_or_text_from_the_home(home):
    calibrate.predict(home, "secret plan about the flat", 70, today=D)
    md = numbers.render(numbers.build(home, commands=3), today=D)
    assert "secret plan" not in md and "T-2611" not in md and str(home) not in md
    assert "2026-11-24" in md and "Engine in numbers" in md


def test_cli_writes_page_and_prints_json(home, tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("LIFEOS_HOME", str(home))
    out = tmp_path / "numbers.md"
    assert main(["numbers", "--out", str(out)]) == 0
    assert "Engine in numbers" in out.read_text(encoding="utf-8")
    capsys.readouterr()
    assert main(["numbers", "--json"]) == 0
    assert '"guard"' in capsys.readouterr().out
