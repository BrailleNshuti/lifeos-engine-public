"""Break-the-guard test (round 4 item 29): every privacy pattern must have a sample that only it catches.

For each pattern the test shows the sample is found, then switches that one pattern off and shows the finding is gone.
A pattern nobody tests, or one another pattern silently covers, fails here. A new pattern without a sample fails too.
All samples are made up and assembled at run time, so no real-looking secret is stored in the repository."""
import re

import pytest

from lifeos import guard

NEVER = re.compile(r"(?!)")

TOKEN_SAMPLES = {
    "GitHub token": "ghp" + "_" + "A1" * 18,
    "API key (sk-)": "sk" + "-" + "abcDEF1234567890abcdEFGH12",
    "Slack token": "xox" + "b-" + "1234567890-abcdefghij",
    "AWS access key": "AKIA" + "ABCDEFGHIJKLMNOP",
    "Google API key": "AIza" + "B" * 35,
    "Private key": "-----BEGIN " + "PRIVATE KEY-----",
    "Basic authorization header": "Authorization: Basic " + "dXNlcjpwYXNzd29yZA==",
    "Long key or secret value": "secret=" + "a1" * 16,
    "JSON web token": "eyJ" + "abcdefgh" + ".eyJ" + "abcdefgh" + "." + "abcdefgh",
    "Social security number": "123-45-" + "6789",
}
# kind -> (module attribute that holds the pattern, a made-up sample)
OTHER_SAMPLES = {
    "ID or passport number": ("ID_DOCUMENT", "passport no: C01" + "X00T47"),
    "Tax or social security number": ("TAX_ID", "tax id: 1234" + "5678901"),
    "PIN": ("PIN", "pin is 48" + "21"),
    "IBAN": ("IBAN_CANDIDATE", "DE89 3704 0044 " + "0532 0130 00"),
    "Card number": ("CARD_CANDIDATE", "4111 1111 " + "1111 1111"),
    "Assigned secret": ("SECRET_ASSIGNMENT", "password: hunter2" + "hunter2"),
    "Email address": ("EMAIL", "write to a.person@" + "example.org please"),
    "Phone number": ("PHONE", "call +49 170 " + "1234567 now"),
}


def kinds(text):
    return {f[2] for f in guard.scan_text(text, allow_mark=False)}


def test_every_token_pattern_has_a_sample():
    assert {k for k, _ in guard.TOKEN_PATTERNS} == set(TOKEN_SAMPLES), "add a sample for the new pattern"


@pytest.mark.parametrize("kind", sorted(TOKEN_SAMPLES))
def test_a_token_sample_is_found_and_only_by_its_own_pattern(kind, monkeypatch):
    sample = f"value {TOKEN_SAMPLES[kind]} end"
    assert kind in kinds(sample)
    monkeypatch.setattr(guard, "TOKEN_PATTERNS", [(k, p) for k, p in guard.TOKEN_PATTERNS if k != kind])
    assert kind not in kinds(sample)


@pytest.mark.parametrize("kind", sorted(OTHER_SAMPLES))
def test_each_other_pattern_is_found_and_switching_it_off_loses_it(kind, monkeypatch):
    attr, sample = OTHER_SAMPLES[kind]
    assert kind in kinds(sample)
    monkeypatch.setattr(guard, attr, NEVER)
    if attr == "CARD_CANDIDATE":
        monkeypatch.setattr(guard, "CARD_DOTTED", NEVER)
    assert kind not in kinds(sample)


def test_the_dotted_card_form_has_its_own_sample(monkeypatch):
    sample = "card 4111.1111." + "1111.1111 end"
    assert "Card number" in kinds(sample)
    monkeypatch.setattr(guard, "CARD_DOTTED", NEVER)
    assert "Card number" not in kinds(sample)


def test_every_module_level_pattern_is_covered_here():
    named = {attr for attr, _ in OTHER_SAMPLES.values()} | {"CARD_DOTTED", "DIFF_INDEX"}
    module_patterns = {n for n, v in vars(guard).items() if isinstance(v, re.Pattern) and n.isupper()}
    assert module_patterns <= named | {"NEVER"}, f"patterns with no sample: {sorted(module_patterns - named)}"


def test_the_diff_header_exemption_matters(monkeypatch):
    line = "index fda0c5c.." + "595" + "9218 100644"
    assert kinds(line) == set()
    monkeypatch.setattr(guard, "DIFF_INDEX", NEVER)
    assert "Card number" in kinds(line), "the sample must pass the card checksum, or the exemption proves nothing"
