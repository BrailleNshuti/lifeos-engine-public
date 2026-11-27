"""`today` warns when no backup was made for 14 days; `selfcheck` says how to fix each kind of damage (round 5 items 3 and 4)."""
import datetime as dt
import json

import pytest

from lifeos import backup, selfcheck, today

D = dt.date(2026, 11, 28)


@pytest.fixture
def home(tmp_path):
    (tmp_path / "logs").mkdir()
    (tmp_path / "tasks").mkdir()
    (tmp_path / "now.md").write_text("# now", encoding="utf-8")
    (tmp_path / "logs" / "ledger.csv").write_text("date,task\n", encoding="utf-8")
    return tmp_path


def test_never_backed_up_is_reported_and_a_backup_resets_it(home, tmp_path_factory):
    assert backup.age_days(home, D) is None
    assert "Backup: never made" in today.render(today.build(home, D))
    backup.make(home, tmp_path_factory.mktemp("out"), today=D)
    assert backup.age_days(home, D) == 0
    assert "Backup:" not in today.render(today.build(home, D))


def test_an_old_backup_is_overdue_after_fourteen_days_not_before(home):
    (home / ".last-backup").write_text("2026-11-14\n", encoding="utf-8")
    assert "Backup:" not in today.render(today.build(home, D))
    (home / ".last-backup").write_text("2026-11-13\n", encoding="utf-8")
    assert "Backup: 15 days old" in today.render(today.build(home, D))


def test_a_garbled_stamp_counts_as_never(home):
    (home / ".last-backup").write_text("yesterday", encoding="utf-8")
    assert backup.age_days(home, D) is None


def test_the_stamp_is_not_part_of_the_backed_up_logs(home, tmp_path_factory):
    folder = backup.make(home, tmp_path_factory.mktemp("out"), today=D)
    assert not list(folder.rglob(".last-backup"))


def test_selfcheck_names_the_fix_for_each_kind_of_damage(home):
    (home / "waiting.json").write_text("{broken", encoding="utf-8")
    (home / "logs" / "ratings.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    text = selfcheck.render(selfcheck.run(home))
    assert "fix waiting:" in text and "fix ratings:" in text
    assert "fix ledger:" not in text


def test_a_sound_home_prints_no_fix_lines(home):
    assert "fix " not in selfcheck.render(selfcheck.run(home))
