"""Canary test (round 4 item 20): text planted in me.md, now.md and a note must never reach any cloud seat's input unless
`--full` is given, and then only the two core files. Every cloud seat is stubbed; nothing leaves the machine. Made-up text."""
import datetime as dt
import shutil

import pytest

from lifeos import ask, seats

TODAY = dt.date(2026, 11, 27)
ME, NOW, NOTE = "CANARY-ME-" + "7f3a9c", "CANARY-NOW-" + "5d21be", "CANARY-NOTE-" + "c0ffee"


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    with open(target / "me.md", "a", encoding="utf-8") as fh:
        fh.write(f"\nA private line: {ME}\n")
    with open(target / "now.md", "a", encoding="utf-8") as fh:
        fh.write(f"\nA private line: {NOW}\n")
    (target / "reviews").mkdir(exist_ok=True)
    (target / "reviews" / "private-note.md").write_text(f"{NOTE}\n", encoding="utf-8")
    return target


@pytest.mark.parametrize("seat", sorted(seats.REMOTE))
def test_the_default_pack_never_carries_me_now_or_a_note(home, seat):
    seen = []

    def stub(prompt):
        seen.append(prompt)
        return "ANSWER. Next: none. https://example.org 2026"
    ask.run_ask(home, seat, "T-261116", adapters={seat: stub}, today=TODAY)
    assert len(seen) == 1
    for canary in (ME, NOW, NOTE):
        assert canary not in seen[0], f"{canary} reached {seat}"


@pytest.mark.parametrize("seat", sorted(seats.REMOTE - {"grok"}))
def test_only_full_adds_the_two_core_files_and_still_not_a_note(home, seat):
    seen = []
    ask.run_ask(home, seat, "T-261116", adapters={seat: lambda p: seen.append(p) or "ANSWER. Next: none. 2026"}, today=TODAY, full=True)
    assert ME in seen[0] and NOW in seen[0] and NOTE not in seen[0]


def test_grok_never_gets_me_or_now_even_with_full(home):
    seen = []
    with pytest.raises(ask.Blocked, match="never sent"):
        ask.run_ask(home, "grok", "T-261116", adapters={"grok": lambda p: seen.append(p) or "x"}, today=TODAY, full=True)
    assert seen == []
