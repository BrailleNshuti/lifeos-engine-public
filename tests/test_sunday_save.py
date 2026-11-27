"""`lifeos sunday --save` keeps the weekly page as a file (round 4 item 27). Made-up data only."""
import datetime as dt
import shutil

import pytest

from lifeos import sunday
from lifeos.cli import main

D = dt.date(2026, 11, 29)


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def test_the_week_file_is_named_by_iso_week(home):
    assert sunday.week_file(home, D).name == "week-2026-W48.md"
    assert sunday.week_file(home, dt.date(2027, 1, 1)).name == "week-2026-W53.md"


def test_save_writes_the_page_and_a_second_run_replaces_it(home):
    path = sunday.save(home, D)
    first = path.read_text(encoding="utf-8")
    assert first.startswith("Sunday review, 2026-11-29")
    assert sunday.save(home, D) == path
    assert path.read_text(encoding="utf-8") == first
    assert len(list((home / "reports").glob("week-*.md"))) == 1


def test_a_page_with_a_secret_is_refused_and_nothing_is_written(home, monkeypatch):
    fake = "sk-" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4"
    monkeypatch.setattr(sunday, "build", lambda h, t=None: "Sunday review\nkey " + fake)
    with pytest.raises(sunday.SaveRefused):
        sunday.save(home, D)
    assert not (home / "reports" / sunday.week_file(home, D).name).exists()


def test_the_command_prints_the_page_and_names_the_file(home, capsys):
    assert main(["--home", str(home), "sunday", "--save"]) == 0
    out = capsys.readouterr().out
    assert "Sunday review" in out and "saved: reports" in out
    main(["--home", str(home), "sunday"])
    assert "saved:" not in capsys.readouterr().out


def test_the_weekly_page_lists_what_is_waiting_with_days_left(home):
    import json
    (home / "waiting.json").write_text(json.dumps([{"item": "pick a date", "who": "you", "when": "2026-12-01"},
                                                   {"item": "later", "who": "you", "when": "anytime"}]), encoding="utf-8")
    page = sunday.build(home, D)
    assert "Waiting\n- pick a date (you, 2026-12-01, in 2 days)\n- later (you, anytime)" in page


def test_an_empty_waiting_list_says_so(home):
    assert "Waiting\nNothing is waiting." in sunday.build(home, D)
