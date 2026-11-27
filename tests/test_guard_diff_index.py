"""A git diff `index` header must not be read as a card number, or a code review of a commit is blocked at random (found when a
real blind review pack was refused on 2026-11-27). Real card numbers in other lines are still blocked."""
import subprocess
from pathlib import Path

import pytest

from lifeos import guard

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("line", ["index fda0c5c.." + "595" + "9218 100644", "index 0000000..1234567", "  index abcdef0123456789..0123456789abcdef 100755  "])
def test_diff_index_lines_are_not_cards(line):
    assert [f for f in guard.scan_text(line) if f[2] == "Card number"] == []


def test_a_real_card_number_is_still_blocked_in_every_other_shape():
    card = "4111 1111 " + "1111 1111"
    for text in (card, "the index is " + card, "index " + card, "index fda0c5c.." + card):
        assert [f for f in guard.scan_text(text) if f[2] == "Card number"], text


def test_a_whole_diff_of_this_repository_has_no_card_findings():
    done = subprocess.run(["git", "log", "-p", "-n", "40", "--format=%H"], capture_output=True, text=True, cwd=ROOT, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        pytest.skip("not a git checkout")
    cards = [f for f in guard.scan_text(done.stdout) if f[2] == "Card number"]
    assert cards == [], cards[:3]
