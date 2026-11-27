"""A long answer that stops mid-sentence is flagged by the free check (round 4 item 16). Made-up text only."""
from lifeos.check import check_answer, looks_cut_off

BODY = "This is a plain sentence that explains the result in some detail. " * 8


def test_a_long_answer_that_stops_mid_sentence_is_flagged():
    cut = BODY + "The next step is to open the file and then compare the two lists of"
    assert looks_cut_off(cut)
    assert any("cut off" in f for f in check_answer(cut + " next", ""))


def test_a_finished_answer_is_not_flagged():
    assert not looks_cut_off(BODY + "That is the whole result.")
    assert not looks_cut_off(BODY + "Done!")
    assert not looks_cut_off(BODY + "Is that clear?")


def test_lists_headings_links_tables_and_code_are_left_alone():
    for tail in ("- first item of the list without a full stop at the end of it all",
                 "1. first numbered item without a full stop at the end of it all",
                 "https://example.org/a-very-long-link-with-no-full-stop-at-the-end",
                 "| column one | column two | column three | column four | five",
                 "# A heading that is long but is not a sentence at all really"):
        assert not looks_cut_off(BODY + "\n" + tail), tail
    assert not looks_cut_off(BODY + "\n```\ncode\n```")


def test_short_answers_are_never_flagged():
    assert not looks_cut_off("a short answer that ends without a stop")
    assert not looks_cut_off("")
