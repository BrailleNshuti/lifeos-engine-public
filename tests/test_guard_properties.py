"""Property-style checks for the privacy guard: many generated, checksum-valid identifiers in many layouts.

All values are made up by a seeded generator at run time, so no real identifier is stored in this file.
"""
import random
import string

import pytest

from lifeos.guard import scan_text

RND = random.Random(20261118)


def blocked(text):
    return any(severity == "BLOCK" for _, severity, _, _ in scan_text(text))


def make_iban(country, length):
    bban = "".join(RND.choice(string.digits) for _ in range(length))
    digits = "".join(str(int(c, 36)) for c in bban + country + "00")
    return f"{country}{98 - int(digits) % 97:02d}{bban}"


def make_card(prefix, total):
    body = prefix + "".join(RND.choice(string.digits) for _ in range(total - len(prefix) - 1))
    s = 0
    for i, c in enumerate(reversed(body)):
        d = int(c)
        if i % 2 == 0:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        s += d
    return body + str((10 - s % 10) % 10)


def grouped(value, size=4, sep=" "):
    return sep.join(value[i:i + size] for i in range(0, len(value), size))


IBAN_SPECS = [("DE", 18), ("GB", 18), ("FR", 23), ("ES", 20), ("NL", 14), ("IT", 23), ("BE", 12), ("AT", 16)]
CARD_SPECS = [("4", 16), ("51", 16), ("37", 15), ("6011", 16), ("35", 16), ("4", 13)]

IBAN_LAYOUTS = {
    "plain": lambda v: v,
    "grouped": grouped,
    "lowercase": lambda v: v.lower(),
    "lowercase grouped": lambda v: grouped(v).lower(),
    "dashes": lambda v: grouped(v, sep="-"),
    "dots": lambda v: grouped(v, sep="."),
    "sentence": lambda v: f"Please pay to {grouped(v)}.",
    "after colon": lambda v: f"IBAN:{v}",
}
CARD_LAYOUTS = {
    "plain": lambda v: v,
    "spaced": grouped,
    "dashes": lambda v: grouped(v, sep="-"),
    "dots": lambda v: grouped(v, sep="."),
    "end of sentence": lambda v: f"My card is {grouped(v)}.",
    "end of sentence plain": lambda v: f"n={v}.",
    "brackets": lambda v: f"({grouped(v)})",
}


@pytest.mark.parametrize("layout", list(IBAN_LAYOUTS))
def test_valid_ibans_are_blocked_in_every_layout(layout):
    for country, length in IBAN_SPECS:
        for _ in range(15):
            value = make_iban(country, length)
            assert blocked(IBAN_LAYOUTS[layout](value)), (layout, country)


@pytest.mark.parametrize("layout", list(CARD_LAYOUTS))
def test_valid_cards_are_blocked_in_every_layout(layout):
    for prefix, total in CARD_SPECS:
        for _ in range(15):
            value = make_card(prefix, total)
            if layout == "dots" and total not in (16, 15, 13):
                continue
            assert blocked(CARD_LAYOUTS[layout](value)), (layout, prefix)


@pytest.mark.parametrize("text", [
    "released 2026-11-18 at 01:13",
    "commit 8feecc5a1b2c3d4e5f60718293a4b5c6d7e8f901",
    "version 0.3.0 and 10.20.30.40",
    "a decimal 4111111111111111.5 stays a number",
    "ratio 1234.5678.9012 is not a card",
    "the rule 12 says no personal data",
    "be12 is a short word pair",
])
def test_ordinary_text_is_not_blocked(text):
    assert not blocked(text)
