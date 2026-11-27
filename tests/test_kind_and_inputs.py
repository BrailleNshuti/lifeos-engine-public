"""T4, T5 and T6: the kind line of a task file, the inputs of the free check, and the quote check at its edges."""
import pytest

from lifeos import check, learn


@pytest.mark.parametrize("raw,expected", [
    ("---\nkind: document review\n---\n", "document review"),
    ("---\r\nkind: document review\r\n---\r\n", "document review"),
    ("---\nkind:    spaced out   \n---\n", "spaced out   "),
    ("---\nid: T-1\n---\nno kind here\n", None),
    ("", None),
    (None, None),
    ("---\nkind:\n---\n", None),
])
def test_explicit_kind_reads_the_line(raw, expected):
    assert learn.explicit_kind(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("  code\nreview, with commas  ", "code review with commas"),
    ("a" * 200, "a" * 80),
    ("", ""),
    (None, ""),
    ("tabs\tand   spaces", "tabs and spaces"),
])
def test_clean_kind_is_one_short_line_without_commas(raw, expected):
    assert learn.clean_kind(raw) == expected


def test_a_crlf_task_file_gives_its_done_when(tmp_path):
    task = tmp_path / "T-1.md"
    task.write_bytes(b"---\r\nid: T-1\r\ndone_when: a URL and a date\r\nstatus: inbox\r\n---\r\n## Context\r\nbody\r\n"
                     b"\r\n## Result (written back here)\r\nold answer\r\n")
    done_when, source = check.task_check_inputs(task)
    assert done_when == "a URL and a date"
    assert "body" in source and "old answer" not in source and "\r" not in source


def test_a_task_without_done_when_gives_an_empty_one(tmp_path):
    task = tmp_path / "T-2.md"
    task.write_text("---\nid: T-2\n---\ncontext\n", encoding="utf-8")
    assert check.task_check_inputs(task)[0] == ""


FILLER = "x"
LINE = "hat sich innerhalb von zwei Wochen nach dem Einzug anzumelden"


def source_of(length):
    return LINE + (" " + FILLER * length)[: length - len(LINE)] if length > len(LINE) else LINE


def flags(text, source):
    return [f for f in check.check_answer(text, source=source) if "quoted" in f]


def test_quotes_are_checked_at_exactly_the_minimum_context():
    text = f'It says "{LINE}". Read 2026-11-26. Next step: none.'
    wrong = f'It says "{LINE} but different". Read 2026-11-26. Next step: none.'
    assert len(source_of(check.QUOTE_MIN_SOURCE)) == check.QUOTE_MIN_SOURCE
    assert flags(wrong, source_of(check.QUOTE_MIN_SOURCE))  # at the minimum the check runs
    assert not flags(wrong, source_of(check.QUOTE_MIN_SOURCE - 1))  # one character less and it does not
    assert not flags(text, source_of(check.QUOTE_MIN_SOURCE))  # a real quote passes at the minimum


@pytest.mark.parametrize("quote,counted", [
    ("short quote here", False),  # under 25 characters
    ("a quote of exactly twenty-5", True),  # 27 characters
])
def test_only_quotes_of_25_characters_or_more_are_counted(quote, counted):
    source = "padding " * 250
    text = f'Read 2026-11-26. "{quote}". Next step: none.'
    assert bool(flags(text, source)) is counted


def test_curly_quotes_are_checked_like_straight_ones():
    source = "padding " * 250 + LINE
    good = f"It says “{LINE}”. Read 2026-11-26. Next step: none."
    bad = f"It says “{LINE} and more words”. Read 2026-11-26. Next step: none."
    assert not flags(good, source)
    assert flags(bad, source)


def test_two_quotes_one_missing_is_one_of_two():
    source = "padding " * 250 + LINE
    text = f'"{LINE}" and "this other line is not in the source at all". Read 2026-11-26. Next step: none.'
    found = flags(text, source)
    assert found and "1 of 2" in found[0]
