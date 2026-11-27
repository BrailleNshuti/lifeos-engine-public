"""T17: the free answer check never raises, whatever text it is given, and its flags are always short strings."""
import random
import string

import pytest

from lifeos import check

SEED = 20261127
ALPHABET = string.printable + "äöüß’“”日本語\U0001f600\x00"


def random_text(rng, n):
    return "".join(rng.choice(ALPHABET) for _ in range(n))


def test_random_text_never_raises_and_flags_are_short_strings():
    rng = random.Random(SEED)
    for _ in range(400):
        text = random_text(rng, rng.randint(0, 600))
        flags = check.check_answer(text, done_when=random_text(rng, rng.randint(0, 80)), source=random_text(rng, rng.randint(0, 2000)))
        assert isinstance(flags, list)
        assert all(isinstance(f, str) and 0 < len(f) < 200 for f in flags)


@pytest.mark.parametrize("value", [None, "", " ", "\n", "\x00", "x" * 100000])
def test_odd_inputs_never_raise(value):
    check.check_answer(value, done_when=value, source=value)


def test_quote_report_on_random_quotes_never_raises():
    rng = random.Random(SEED + 1)
    for _ in range(200):
        text = f'say "{random_text(rng, 30)}" and “{random_text(rng, 40)}”'
        found, missing = check.quote_report(text, random_text(rng, 500))
        assert isinstance(found, list) and isinstance(missing, list)


def test_the_same_input_gives_the_same_flags():
    text = "I'll save it. Fixed. See https://x.example with 3 items"
    assert check.check_answer(text, "a URL and a date") == check.check_answer(text, "a URL and a date")


def test_a_very_long_answer_is_checked_quickly():
    import time
    start = time.perf_counter()
    check.check_answer("word " * 200000, done_when="a URL and a date", source="word " * 2000)
    assert time.perf_counter() - start < 3.0
