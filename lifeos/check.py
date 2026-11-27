
"""A free sanity check for model answers: plain text rules, no model call, no tokens.

It catches the usual nonsense (empty, refusals, echoed prompt, success without proof, undated links, guessing, no next step).
It does not prove an answer right; it tells Claude and you where to look first (rules 1 and 6).
Since the first week of real use it also reads the task's done_when (does the answer carry the URL or date it asks for?)
and the text the seat was given (are the quoted lines really there?), and flags a seat that only promises to save.
"""
import re
from pathlib import Path

from .store import read_text_retry

REFUSAL = r"can'?t access|cannot|can not|as an ai\b|unable to|don'?t have access|no access"
SUCCESS = r"\b(done|completed?|fixed|works?|verified|all tests pass(ed)?|resolved)\b"
EVIDENCE = r"\d|https?://|```|`[^`]+`|\w+\.(py|md|js|ts|csv|json|yml|txt)\b"
HEDGE = r"probably|should work|should be fine|i assume|i think|might|maybe|likely"


PROMISE = re.compile(r"\b(?:i['’]?ll|i will|i am going to|i['’]?m going to)\s+(?:now\s+)?(?:save|record|write|store|log)\b", re.I)
QUOTE = re.compile("[\"\u201c]([^\"\u201c\u201d\n]{25,}?)[\"\u201d]")
LONG_ANSWER = 8000  # characters
QUOTE_MIN_SOURCE = 1500  # below this the task only points at pages; the quotes cannot be checked against it
BACKTICK = re.compile(r"`([^`\n]{40,}?)`")  # only for verify-quotes: a long span with a space is a quoted line, a path is not
URL = re.compile(r"https?://", re.I)
DATE = re.compile(r"\b20\d\d-\d\d-\d\d\b|\b\d{1,2}\.\s?\d{1,2}\.\s?20\d\d\b|\b20\d\d\b")


def _squash(text):
    return " ".join(str(text).split()).casefold()


def task_check_inputs(path):
    """(done_when, context) of a task file: what the answer must carry and the text the seat was given. Never raises."""
    try:
        raw = read_text_retry(path)
    except (OSError, UnicodeError):
        return "", ""
    raw = raw.replace("\r\n", "\n")
    match = re.search(r"^done_when:[ \t]*(.*)$", raw, re.M)
    done_when = match.group(1).strip() if match else ""
    return done_when, raw.split("\n## Result", 1)[0]


WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
COUNTED = re.compile(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|\d{1,2})\s+(?:[\w-]+\s+){0,2}?"
                     r"(items?|points?|steps?|causes?|claims?|examples?|ways|options|reasons|lines|bullets|findings|risks|ideas)\b", re.I)
LIST_ITEM = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+\S", re.M)
NEEDS_NUMBER = re.compile(r"\b(?:a|the|exact)\s+(?:number|figure|price|cost|amount|percentage)\b|\bhow (?:many|much)\b", re.I)


def _structured_flags(text, wanted):
    """Parts of a done_when the free check can test: a counted list ("three causes") and a requested number."""
    flags = []
    asked = COUNTED.search(wanted)
    if asked:
        n = WORD_NUMBERS.get(asked.group(1).lower()) or int(asked.group(1))
        have = len(LIST_ITEM.findall(text))
        if have and have < n:
            flags.append(f"done_when asks for {n} {asked.group(2).lower()}; the answer lists {have}")
    if NEEDS_NUMBER.search(wanted) and not re.search(r"\d", text):
        flags.append("done_when asks for a number; the answer has none")
    return flags


def _done_when_flags(text, done_when):
    wanted = (done_when or "").strip()
    if not wanted or wanted.upper().startswith("TODO"):
        return []
    flags = []
    if re.search(r"\burls?\b|\blink", wanted, re.I) and not URL.search(text):
        flags.append("done_when asks for a URL; the answer has none")
    if re.search(r"\bdated?\b", wanted, re.I) and not DATE.search(text):
        flags.append("done_when asks for a date; the answer has none")
    return flags + _structured_flags(text, wanted)


def quote_report(text, source, backticks=False):
    """(found, missing): the quoted lines (25 characters or more) of an answer that are, and are not, in the source.
    Case and spacing are ignored. With `backticks` a long span in backticks that holds a space also counts as a quote.
    No minimum length of the source here; `_quote_flags` adds that rule and never reads backticks."""
    haystack = _squash(source or "")
    spans = [m.group(1) for m in QUOTE.finditer(text or "")]
    if backticks:
        spans += [m.group(1) for m in BACKTICK.finditer(text or "") if " " in m.group(1).strip()]
    found, missing = [], []
    for span in spans:
        (found if _squash(span) in haystack else missing).append(span)
    return found, missing


def _quote_flags(text, source):
    if len(source or "") < QUOTE_MIN_SOURCE:  # a seat that fetched its own pages quotes text we never gave it
        return []
    found, missing = quote_report(text, source)
    if not missing:
        return []
    return [f"{len(missing)} of {len(found) + len(missing)} quoted lines not found in the task context (check them by hand)"]


CUT_MIN = 400  # characters; a short answer may end any way it likes


def looks_cut_off(text):
    """True when a long answer stops in the middle of a sentence: the last line is plain prose (no list marker, heading,
    link, table or code) and ends on a letter, a digit, a comma or an open bracket. A seat that hit its output limit does this."""
    text = (text or "").strip()
    if len(text) < CUT_MIN or text.endswith("```"):
        return False
    last = text.splitlines()[-1].strip()
    if len(last) < 30 or re.match(r"^([-*>#|]|\d+[.)]\s)", last) or "http" in last or "`" in last:
        return False
    return bool(re.search(r"[A-Za-z0-9,(\[]$", last)) and last.count(" ") >= 4


def check_answer(text, done_when="", source=""):
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
    if looks_cut_off(text):
        flags.append("the answer seems cut off mid-sentence: ask again for the rest or for a shorter answer")
    if len(text) > LONG_ANSWER:
        flags.append(f"very long answer ({len(text):,} characters): ask for the short version")
    if not re.search(r"next", text, re.I):
        flags.append("no next step")
    if PROMISE.search(text) and len(text) < 600:
        flags.append("promises to save the result instead of giving it (the seat cannot write)")
    return flags + _done_when_flags(text, done_when) + _quote_flags(text, source)
