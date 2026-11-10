from lifeos.week import render_markdown, week_bounds, week_numbers


def test_week_bounds():
    start, end = week_bounds("2026-W47")
    assert (start.isoformat(), end.isoformat()) == ("2026-11-16", "2026-11-22")


def test_week_numbers_come_only_from_the_logs(demo):
    n = week_numbers(demo, "2026-W47")
    assert n["proofs"] == 3 and n["proofs_by_area"] == {"career": 2, "german": 1}
    assert n["ledger_lines"] == 3 and n["net_hours_saved"] == 1.0
    assert "Proofs: 3 (career 2, german 1)" in render_markdown(n)


def test_empty_week_says_none(demo):
    assert "none this week" in render_markdown(week_numbers(demo, "2026-W40"))
