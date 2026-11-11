"""A free sanity check for model answers: plain text rules, no model call, no tokens.

It catches the usual nonsense (empty, refusals, echoed prompt, success without proof, undated links, guessing, no next step).
It does not prove an answer right; it tells Claude and you where to look first (rules 1 and 6).
"""
import re

REFUSAL = r"can'?t access|cannot|can not|as an ai\b|unable to|don'?t have access|no access"
SUCCESS = r"\b(done|completed?|fixed|works?|verified|all tests pass(ed)?|resolved)\b"
EVIDENCE = r"\d|https?://|```|`[^`]+`|\w+\.(py|md|js|ts|csv|json|yml|txt)\b"
HEDGE = r"probably|should work|should be fine|i assume|i think|might|maybe|likely"


def check_answer(text):
    """Return a list of short flags. An empty list means nothing obvious is wrong."""
    text = (text or "").strip()
    if not text:
        return ["empty answer"]
    if len(text) < 15:
        return ["answer is too short to be a result"]
    flags = []
    if re.search(REFUSAL, text, re.I):
        flags.append("model could not do the job (refusal or no access)")
    if "Use only the context given" in text:
        flags.append("repeated the prompt instead of answering")
    if re.search(SUCCESS, text, re.I) and not re.search(EVIDENCE, text, re.I):
        flags.append("claims success without evidence (rule 1)")
    if re.search(r"https?://", text) and not re.search(r"\b20\d\d\b", text):
        flags.append("link without a date (rule 6)")
    if len(re.findall(HEDGE, text, re.I)) >= 2:
        flags.append("mostly guesses, not evidence")
    if not re.search(r"next", text, re.I):
        flags.append("no next step")
    return flags
