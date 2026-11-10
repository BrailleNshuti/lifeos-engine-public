import re
from lifeos.guard import iban_valid, luhn_valid, scan_text

# Secrets are assembled at runtime, so this file itself never trips the guard in CI.
IBAN = "DE89 3704 " + "0044 0532 0130 00"
CARD = " ".join(["4111"] + ["1111"] * 3)


def kinds(text, **kw):
    return {(severity, kind) for _, severity, kind, _ in scan_text(text, **kw)}


def test_checksums():
    assert iban_valid(IBAN) and not iban_valid("DE00" + " 1234" * 4)
    assert luhn_valid(CARD) and not luhn_valid("4111" + "1111" * 2 + "1112")


def test_blocks_class_c_data():
    assert ("BLOCK", "IBAN") in kinds(f"rent goes to {IBAN}")
    assert ("BLOCK", "Card number") in kinds(f"card {CARD}")
    assert ("BLOCK", "GitHub token") in kinds("token " + "ghp_" + "a1" * 18)
    assert ("BLOCK", "API key (sk-)") in kinds("key " + "sk-ant-" + "x" * 30)
    assert ("BLOCK", "Private key") in kinds("-----BEGIN " + "RSA PRIVATE KEY-----")
    assert ("BLOCK", "ID or passport number") in kinds("Passport: " + "C01X00T47")


def test_warns_but_does_not_block():
    found = kinds("write to alex" + "@" + "example.org or call +49 " + "151 2345 6789")
    assert ("WARN", "Email address") in found and ("WARN", "Phone number") in found
    assert not any(severity == "BLOCK" for severity, _ in found)


def test_clean_text_and_ordinary_numbers_pass():
    text = "Gate 1 on 2026-12-06; 154 to 172 hours; version 2.3; 1,129 skills; ISO week 2026-W47"
    assert kinds(text) == set()


def test_allow_mark_and_private_patterns():
    assert kinds(f"{IBAN}  # lifeos-guard: allow") == set()
    street = re.compile("musterstra(ss|ß)e 12", re.I)
    assert ("BLOCK", "Private pattern") in kinds("I live at Musterstrasse 12", private=[street])
