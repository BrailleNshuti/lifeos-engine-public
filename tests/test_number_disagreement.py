"""Two seats' answers to one task: numbers that differ are pointed out (round 4 item 22). Made-up text only."""
from lifeos import notes


def doc(*blocks):
    return "---\nid: T-1\n---\nGoal\n" + "".join(f"\n## Result · {who} · 2026-11-27\n{body}\n" for who, body in blocks)


def test_a_shared_number_and_two_different_ones_are_flagged():
    raw = doc(("grok", "The fine is up to 1,000 euros and the deadline is 14 days."),
              ("claude", "The deadline is 14 days. The fine is up to 5,000 euros."))
    out = notes.disagreements(raw)
    assert len(out) == 1 and "claude and grok" in out[0] and "5000" in out[0] and "1000" in out[0]


def test_the_same_numbers_are_not_flagged():
    raw = doc(("grok", "Deadline 14 days, fine 1,000 euros."), ("claude", "The fine is 1000 euros; the deadline is 14 days."))
    assert notes.disagreements(raw) == []


def test_answers_with_nothing_in_common_are_left_alone():
    raw = doc(("grok", "It costs 120 euros."), ("claude", "The meeting is on 2026-12-08 at 14:30 with 12 people."))
    assert notes.disagreements(raw) == []


def test_one_answer_or_the_same_seat_twice_is_not_compared():
    assert notes.disagreements(doc(("grok", "fine 1000, days 14"))) == []
    assert notes.disagreements(doc(("grok", "fine 1000, days 14"), ("grok", "fine 5000, days 14"))) == []


def test_it_compares_with_the_latest_earlier_answer_of_another_seat():
    raw = doc(("gemini", "total 300 and 45"), ("claude", "total 700 and 45"), ("claude", "total 800 and 45"))
    out = notes.disagreements(raw)
    assert "claude and claude" not in out[0] and "gemini" in out[0]


def test_single_digits_are_ignored_and_decimals_and_thousands_are_read():
    assert notes.numbers_in("step 1 of 3") == set()
    assert notes.numbers_in("Python 3.15 and 1,000 euros in 2026") == {"3.15", "1000", "2026"}


def test_post_notes_adds_the_line_to_the_check(tmp_path):
    path = tmp_path / "T-1.md"
    path.write_text(doc(("grok", "Next: deadline 14 days, fine 1,000 euros https://x.org 2026"),
                        ("claude", "Next: deadline 14 days, fine 5,000 euros https://x.org 2026")), encoding="utf-8")
    assert any(line.startswith("NUMBERS differ") for line in notes.post_notes(path))
