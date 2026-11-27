"""More identifier shapes the guard must stop, and harmless look-alikes it must not. Found by probing with made-up values
(2026-11-27): a US social security number, a JWT, a labelled tax id and a spoken PIN were not blocked.
Values are assembled at run time so this file never trips the guard in CI."""
import pytest

from lifeos.guard import scan_text

SSN = "078" + "-05-" + "1120"
JWT = ".".join(["eyJhbGciOiJIUzI1NiJ9", "eyJzdWIiOiIxMjM0NTY3ODkwIn0", "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"])
TAX_ID = "86095" + "742719"
PIN = "49" + "21"


def blocked(text):
    return [f for f in scan_text(text) if f[1] == "BLOCK"]


@pytest.mark.parametrize("text", [
    f"SSN {SSN}",
    f"social security number: {SSN} on file",
    f"Authorization: Bearer {JWT}",
    f"token in the log {JWT}",
    f"Steuer-ID: {TAX_ID}",
    f"Steuer-Identifikationsnummer {TAX_ID[:3]} {TAX_ID[3:6]} {TAX_ID[6:]}",
    f"my tax id is {TAX_ID}".replace("is ", ": "),
    f"my PIN is {PIN} for the card",
    f"pin: {PIN}",
    f"Geheimzahl = {PIN}",
])
def test_these_are_blocked(text):
    assert blocked(text), text


@pytest.mark.parametrize("text", [
    "range 100-200 and 300-400-500",
    "ISBN 978-3-16-148410-0 is a book",
    "pin the version to 3.12 and pin 4 packages",
    "the pin number was discussed in 2026-11 planning",
    "a tin of 12345678901 nails",
    "eyJ is how every base64 json header starts",
    "date 2026-11-27 and time 14-30-00",
    "phone numbers are warned about, not blocked",
    "Steuer-ID is asked for in the form",
])
def test_these_are_not_blocked(text):
    assert not blocked(text), text
