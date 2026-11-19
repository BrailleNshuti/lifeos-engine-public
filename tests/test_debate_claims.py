"""The scoring unit of a debate is the item the seat wrote (a numbered point with its evidence), not a sentence."""
import pytest

from lifeos import debate

# The shape real answers had in the first live debate: numbered points, sub-bullets, an Evidence line, a closing paragraph.
SHAPED = """1. Yes. `store.write` can raise an error on Windows if another process has the file open.

2. Whether it fails depends on how the reader opened the file. Most callers do not share delete access.

3. You can check this yourself. Process A runs `f = open("a.txt")`. Process B calls `store.write("a.txt")`.

4. The safest pattern is to avoid replacing a file that readers hold open.
   - Write a temp file in the same directory and flush it.
   - Call the replace, and on an error retry with a short backoff.
   - Evidence: the docs say the operation is atomic on POSIX only.

5. For a log that is read continuously, prefer append-only writes.

**What would prove me wrong:** the test in claim 3 succeeding when the reader used plain `open()`.
"""


def test_a_numbered_item_is_one_claim_with_its_sub_lines_attached():
    got = debate.claims_of(SHAPED)
    assert len(got) == 6  # five numbered items and the closing paragraph
    assert got[3].startswith("The safest pattern") and "retry with a short backoff" in got[3] and "atomic on POSIX only" in got[3]
    assert got[2].count("Process A") == 1 and "You can check this yourself" in got[2]


def test_the_closing_paragraph_is_its_own_claim_and_markup_is_stripped():
    last = debate.claims_of(SHAPED)[-1]
    assert last.startswith("What would prove me wrong") and "*" not in last and "`" not in last


def test_identifiers_with_underscores_survive():
    assert debate.claims_of("1. The cap is CALL_CAP in seats_table.py today.") == ["The cap is CALL_CAP in seats_table.py today."]


def test_bullets_without_numbers_are_items_too():
    text = "- First point about the store.\n  more words on it\n- Second point about tests.\n- ok"
    assert debate.claims_of(text) == ["First point about the store. more words on it", "Second point about tests."]


def test_paragraphs_are_items_when_there_is_no_list():
    text = "The store should keep sqlite for speed.\nIt also needs a lock.\n\nTests come first in every change."
    assert debate.claims_of(text) == ["The store should keep sqlite for speed. It also needs a lock.", "Tests come first in every change."]


def test_one_unstructured_paragraph_falls_back_to_sentences():
    got = debate.claims_of("The store should use sqlite. Tests come first. The call cap is 14.")
    assert got == ["The store should use sqlite.", "Tests come first.", "The call cap is 14."]


def test_items_shorter_than_three_words_are_dropped_and_the_cap_holds():
    assert debate.claims_of("1. Yes.\n2. The cap is 14 calls.") == ["The cap is 14 calls."]
    many = "\n".join(f"{i}. Point number {i} is stated here." for i in range(1, 60))
    assert len(debate.claims_of(many)) == debate.MAX_CLAIMS


def test_names_and_hashes_are_still_scrubbed_inside_an_item():
    got = debate.claims_of("1. Ask Claude about " + "ab" * 32 + " before the change.")[0]
    assert "claude" not in got.lower() and "ab" * 32 not in got


def test_a_long_item_is_clipped_only_for_the_table(tmp_path):
    item = "1. " + "word " * 100 + "end."
    assert len(debate.claims_of(item)[0]) > debate.CLIP  # prompts show the whole claim
    assert len(debate.clip(debate.claims_of(item)[0])) <= debate.CLIP and debate.clip("short claim here") == "short claim here"


@pytest.mark.parametrize("answer, expected", [(SHAPED, 6), ("1. A\n2. B\n3. C", 0)])
def test_the_count_matches_what_a_reader_sees(answer, expected):
    assert len(debate.claims_of(answer)) == expected
