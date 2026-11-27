"""Deadlines and the age of now.md, read from now.md, shown by `today` and `next` (round 7 items 12 and 13). Made-up data."""
import datetime as dt

import pytest

from lifeos import deadlines, nextup, today

DAY = dt.date(2026, 11, 28)
NOW = """# Now · week 2026-W48 · updated 2026-11-10

## Areas
- lab: a line that mentions 12 Dec: it is not under Deadlines

## Deadlines (only real outside dates)
- Wed 11 Nov: something that already passed
- Sun 6 Dec: first checkpoint · targets set
- Fri 18 Dec: pay the invoice
- Jan 2027: lease ends
- 1 to 12 Mar 2027: exams (6)
- Someday: no date here
- Mon 31 Feb: an impossible day

## Limits hit: see logs/limits.md
- Tue 1 Dec: not under Deadlines any more
"""


@pytest.fixture
def home(tmp_path):
    (tmp_path / "logs").mkdir()
    (tmp_path / "tasks").mkdir()
    (tmp_path / "now.md").write_text(NOW, encoding="utf-8")
    return tmp_path


def test_lines_are_read_with_the_weekday_choosing_the_year(home):
    got = {d["text"]: d for d in deadlines.read(home, DAY)}
    assert got["first checkpoint"]["date"] == "2026-12-06" and got["first checkpoint"]["days"] == 8
    assert got["pay the invoice"]["date"] == "2026-12-18"
    assert got["something that already passed"]["days"] == -17
    assert got["exams (6)"]["date"] == "2027-03-01"
    assert got["lease ends"] == {"date": "2027-01-01", "text": "lease ends", "approx": True, "days": 34}


def test_unreadable_lines_and_other_sections_are_left_out(home):
    texts = [d["text"] for d in deadlines.read(home, DAY)]
    assert not any("Someday" in t or "impossible" in t or "not under" in t for t in texts)
    assert len(texts) == 5


def test_upcoming_is_from_today_and_within_the_window(home):
    assert [d["text"] for d in deadlines.upcoming(home, DAY, within=30)] == ["first checkpoint", "pay the invoice"]


def test_the_age_of_now_md_comes_from_its_title(home, tmp_path):
    assert deadlines.now_age_days(home, DAY) == 18
    (home / "now.md").write_text("# Now without a date\n", encoding="utf-8")
    assert deadlines.now_age_days(home, DAY) is None
    assert deadlines.now_age_days(tmp_path / "nowhere", DAY) is None


def test_no_file_or_no_section_means_no_deadlines(tmp_path):
    assert deadlines.read(tmp_path, DAY) == []
    (tmp_path / "now.md").write_text("# Now\n## Areas\n- x\n", encoding="utf-8")
    assert deadlines.read(tmp_path, DAY) == []


def test_today_shows_the_deadlines_and_the_stale_now_md(home):
    text = today.render(today.build(home, DAY))
    assert "Deadlines (from now.md)" in text and "2026-12-06: first checkpoint (in 8 days)" in text
    assert "2027-01-01 (about): lease ends" in text
    assert "now.md says it was updated 18 days ago" in text


def test_next_names_a_deadline_within_a_week_and_ignores_approximate_ones(home):
    assert nextup.choose(home, dt.date(2026, 12, 1))["kind"] == "deadline"
    assert nextup.choose(home, DAY)["kind"] == "none"  # the checkpoint is 8 days away, the January date is only about
    assert "first checkpoint" in nextup.render(nextup.choose(home, dt.date(2026, 12, 1)))
