"""The free answer check also reads the task's done_when and the text the seat was given (no model call).

Cases come from the first week of real use (2026-11-26): a seat that only promised to save its answer, a done_when that
asked for a source URL and date, and quoted lines that must exist in what the seat was given.
"""
from lifeos import check

NARRATION = "I'll save the deadline and the fine, each tied to the section I opened. Next step: none."
SOURCE = ("padding " * 250) + "Wer eine Wohnung bezieht, hat sich innerhalb von zwei Wochen nach dem Einzug anzumelden. Fine up to 1000 euros."


def flags(text, done_when="", source=""):
    return check.check_answer(text, done_when=done_when, source=source)


def test_a_seat_that_only_promises_to_save_is_flagged():
    assert any("promises to save" in f for f in flags(NARRATION))


def test_a_real_answer_that_mentions_saving_is_not_flagged():
    text = ("Deadline: 14 days (BMG 17, https://www.gesetze-im-internet.de/bmg/__17.html, read 2026-11-26). "
            "Nothing was saved or written. Next step: open the page.")
    assert not any("promises to save" in f for f in flags(text))


def test_done_when_that_asks_for_a_url_is_checked():
    answer = "The deadline is 14 days and the fine is up to 1000 euros, read on 2026-11-26. Next step: none."
    assert any("url" in f.lower() for f in flags(answer, done_when="deadline and fine, each with a source URL"))
    with_url = answer.replace("none.", "none. Source: https://example.org/law")
    assert not any("url" in f.lower() for f in flags(with_url, done_when="deadline and fine, each with a source URL"))


def test_done_when_that_asks_for_a_date_is_checked():
    answer = "Python 3.15, source https://www.python.org/downloads/. Next step: none."
    assert any("date" in f.lower() for f in flags(answer, done_when="version, date and URL"))
    assert not any("date" in f.lower() for f in flags(answer + " Read 2026-11-26.", done_when="version, date and URL"))


def test_an_empty_done_when_adds_no_flags():
    assert flags("Fixed in lifeos/a.py with 4 tests passing. Next step: review the diff.", done_when="") == []
    assert flags("Fixed in lifeos/a.py with 4 tests passing. Next step: review.", done_when="TODO (you write this line)") == []


def test_quotes_that_are_not_in_the_source_are_counted():
    good = 'It says "hat sich innerhalb von zwei Wochen nach dem Einzug anzumelden". Read 2026-11-26. Next step: none.'
    assert not any("quoted" in f for f in flags(good, source=SOURCE))
    bad = good + ' It also says "a fine of fifty thousand euros applies to every case". '
    found = [f for f in flags(bad, source=SOURCE) if "quoted" in f]
    assert found and "1 of 2" in found[0]


def test_quote_matching_ignores_case_and_spacing():
    text = 'Line: "WER EINE  Wohnung bezieht, hat sich innerhalb". Read 2026-11-26. Next step: none.'
    assert not any("quoted" in f for f in flags(text, source=SOURCE))


def test_short_quotes_are_not_checked():
    text = 'The word "fine" appears. Read 2026-11-26. Next step: none.'
    assert not any("quoted" in f for f in flags(text, source=SOURCE))


def test_task_check_inputs_reads_done_when_and_context(tmp_path):
    task = tmp_path / "T-1.md"
    task.write_text("---\nid: T-1\ngoal: g\ndone_when: version, date and URL\nroute: x\nlevel: L1\nstatus: inbox\n---\n"
                    "## Context (links, not essays)\nSome context line.\n\n## Task\ng\n\n## Result (written back here)\nold\n",
                    encoding="utf-8")
    done_when, source = check.task_check_inputs(task)
    assert done_when == "version, date and URL"
    assert "Some context line." in source and "old" not in source


def test_task_check_inputs_never_raises(tmp_path):
    assert check.task_check_inputs(tmp_path / "missing.md") == ("", "")


def test_quotes_are_not_checked_when_the_task_only_points_at_pages():
    short = "Fetch https://www.gesetze-im-internet.de/bmg/__17.html"
    text = 'The law says "hat sich innerhalb von zwei Wochen nach dem Einzug anzumelden". Read 2026-11-26. Next step: none.'
    assert not any("quoted" in f for f in flags(text, source=short))


def test_a_curly_apostrophe_promise_is_flagged():
    assert any("promises to save" in f for f in flags("Both pages were readable. I’ll save the deadline. Next step: none."))
