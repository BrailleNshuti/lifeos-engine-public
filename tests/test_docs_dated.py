"""T16: figures that change (test counts, module counts) only appear in documents that carry a date in their title."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATE = r"20\d\d-\d\d-\d\d"


def test_the_proof_file_is_dated_and_has_a_verdict():
    first = (ROOT / "docs" / "proof.md").read_text(encoding="utf-8").splitlines()[0]
    assert re.fullmatch(rf"# Proof · {DATE} · (PASS|FAIL)", first), first


def test_the_numbers_page_is_dated():
    head = (ROOT / "docs" / "numbers.html").read_text(encoding="utf-8")[:600]
    assert re.search(rf"<title>Engine in numbers · {DATE}</title>", head)


def test_the_state_file_is_dated():
    first = (ROOT / "STATE.md").read_text(encoding="utf-8").splitlines()[0]
    assert re.fullmatch(rf"# State of lifeos-engine · {DATE}", first), first


def test_the_proof_file_is_not_newer_than_today():
    import datetime as dt
    stamp = re.search(DATE, (ROOT / "docs" / "proof.md").read_text(encoding="utf-8").splitlines()[0]).group(0)
    assert dt.date.fromisoformat(stamp) <= dt.date.today()
