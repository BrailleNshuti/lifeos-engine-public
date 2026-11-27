"""T14 and T15: the seat tables cannot drift apart, and a timeout on the first seat falls over to the next one."""
import shutil

import pytest

from lifeos import ask, delegate, seats
from lifeos.ask import ADAPTERS


def test_every_seat_in_the_cannot_table_is_a_real_seat():
    assert set(seats.CANNOT) <= set(seats.CHAINS)


def test_every_warning_names_its_own_seat():
    for seat, rules in seats.CANNOT.items():
        for _pattern, message in rules:
            assert seat in message.lower(), (seat, message)


def test_every_seat_has_a_description_and_a_chain():
    for seat in seats.CHAINS:
        assert seats.GOOD_AT.get(seat), seat
        assert seats.CHAINS[seat], seat


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def test_a_timeout_on_the_first_seat_falls_over_and_says_timeout(home):
    def slow(prompt):
        raise ask.AskError("codex failed: did not answer within 600 s")

    out = delegate.run_delegate(home, "T-261116", adapters={**ADAPTERS, "codex": slow})
    assert out["tried"][0] == "codex" and len(out["tried"]) >= 2
    assert out["failed"][0]["kind"] == "timeout"
    assert "timeout" in out["reason"] and "fell back" in out["reason"]
