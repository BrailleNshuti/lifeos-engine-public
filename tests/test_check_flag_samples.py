"""One positive and one near miss for every family of free answer-check flag."""
import pytest

from lifeos import check


GOOD = "Evidence: 3 tests passed in lifeos/check.py. Next step: review the diff."
LONG_SOURCE = "The supplied source contains ordinary context. " * 40
FOUND_QUOTE = "The supplied source contains ordinary context"


@pytest.mark.parametrize("expected,text,done_when,source,near_text,near_done,near_source", [
    ("empty answer", "", "", "", GOOD, "", ""),
    ("too short", "ok", "", "", "Next step: done.", "", ""),
    ("could not do", "I cannot access it. Evidence: 2 attempts. Next step: provide access.", "", "",
     "I accessed it. Evidence: 2 attempts. Next step: review.", "", ""),
    ("repeated the prompt", "Use only the context given. Evidence: 2 lines. Next step: answer.", "", "",
     "Used the supplied context. Evidence: 2 lines. Next step: answer.", "", ""),
    ("success without evidence", "Everything is fixed and works. Next step: review.", "", "", GOOD, "", ""),
    ("link without a date", "Source: https://example.com/page. Next step: verify.", "", "",
     "Source (2026): https://example.com/page. Next step: verify.", "", ""),
    ("mostly guesses", "It probably works and might be fine. Evidence: 2 checks. Next step: test.", "", "",
     "It probably works. Evidence: 2 checks. Next step: test.", "", ""),
    ("cut off mid-sentence", "Evidence: 2 tests. Next step: continue. " + "A long explanation remains useful " * 14,
     "", "", "Evidence: 2 tests. Next step: continue. " + "A long explanation remains useful " * 14 + ".", "", ""),
    ("very long answer", "Evidence: 2 tests. Next step: review. " + "word " * 1700, "", "", GOOD, "", ""),
    ("no next step", "Evidence: 2 tests passed in lifeos/check.py. Open issues: none.", "", "", GOOD, "", ""),
    ("promises to save", "I will save this result. Evidence: 2 checks. Next step: wait.", "", "",
     "I saved this result. Evidence: 2 checks. Next step: review.", "", ""),
    ("asks for a URL", GOOD, "a URL to the proof", "", "Evidence: https://example.com/proof (2026). Next step: review.",
     "a URL to the proof", ""),
    ("asks for a date", GOOD, "a dated source", "", "Evidence: source dated 2026-11-28. Next step: review.",
     "a dated source", ""),
    ("asks for 3", "Evidence:\n- one finding\nNext step: add the rest.", "three findings", "",
     "Evidence:\n- one\n- two\n- three\nNext step: review.", "three findings", ""),
    ("asks for a number", "Evidence is attached. Next step: review.", "the exact number", "",
     "Evidence: 42. Next step: review.", "the exact number", ""),
    ("quoted lines not found", f'Claim: "A fabricated sentence that is absent from all supplied context". Next step: verify.',
     "", LONG_SOURCE, f'Claim: "{FOUND_QUOTE}". Next step: verify.', "", LONG_SOURCE),
])
def test_each_flag_family_has_a_trigger_and_a_near_miss(expected, text, done_when, source,
                                                         near_text, near_done, near_source):
    assert any(expected in flag for flag in check.check_answer(text, done_when, source))
    assert not any(expected in flag for flag in check.check_answer(near_text, near_done, near_source))
