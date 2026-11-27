"""The free check tests a counted list and a requested number in done_when (round 4 item 21). Made-up text only."""
from lifeos.check import check_answer


def flags(text, done_when):
    return [f for f in check_answer(text, done_when) if f.startswith("done_when")]


def test_too_few_list_items_are_flagged():
    text = "Causes:\n- the first cause explained at length\n- the second cause explained at length\nNext: check them."
    assert flags(text, "Three causes were listed and each checked") == ["done_when asks for 3 causes; the answer lists 2"]


def test_enough_items_pass_with_digits_or_words_and_numbered_lists():
    text = "1. one thing here\n2. another thing here\n3. a third thing here\nNext: go."
    assert flags(text, "three causes listed") == [] and flags(text, "3 items listed") == []


def test_prose_without_a_list_is_not_second_guessed():
    assert flags("There are three causes: the disk, the scanner and the lock. Next: test.", "three causes listed") == []


def test_a_requested_number_must_appear():
    assert flags("It is cheap. Next: ask again.", "State the price as a number") == ["done_when asks for a number; the answer has none"]
    assert flags("It costs 120 euros. Next: none.", "State the price as a number") == []


def test_todo_and_empty_done_when_stay_silent():
    assert flags("anything at all in here, long enough to count. Next: none", "TODO") == []
    assert flags("anything at all in here, long enough to count. Next: none", "") == []
