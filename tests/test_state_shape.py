"""STATE.md stays readable: a dated title, section headings, and no bullet longer than 400 characters."""
import re
from pathlib import Path

STATE = (Path(__file__).resolve().parents[1] / "STATE.md").read_text(encoding="utf-8").replace("\r\n", "\n")
SECTIONS = ("Now", "Open", "Waiting on the owner", "Release", "Next")


def test_the_title_has_a_date():
    assert re.fullmatch(r"# State of lifeos-engine · 20\d\d-\d\d-\d\d", STATE.splitlines()[0])


def test_every_expected_section_is_there():
    headings = re.findall(r"^## (.+)$", STATE, re.M)
    for name in SECTIONS:
        assert name in headings, name


def test_no_bullet_is_longer_than_400_characters():
    long = [(n, len(line)) for n, line in enumerate(STATE.splitlines(), 1) if line.startswith("- ") and len(line) > 400]
    assert not long, f"lines too long (number, characters): {long}"


def test_the_file_is_not_a_wall_of_text():
    assert len(STATE.splitlines()) < 80
