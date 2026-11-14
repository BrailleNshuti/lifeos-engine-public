"""Tests for lifeos log (proof, ledger, health, hours). All data is synthetic."""
import csv
import shutil

import pytest

from lifeos import log
from lifeos.cli import main


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def test_log_proof_appends_valid_row_and_prints(home, capsys):
    rc = main([
        "--home", str(home), "log", "proof",
        "--area", "study",
        "--proof", "Finished Unit 1 summary",
        "--link", "https://example.org/proof-1",
        "--date", "2026-11-18",
    ])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out == "2026-11-18,study,Finished Unit 1 summary,https://example.org/proof-1"
    raw = (home / "logs" / "proofs.csv").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in raw
    rows = list(csv.DictReader((home / "logs" / "proofs.csv").read_text(encoding="utf-8").splitlines()))
    assert rows[-1] == {
        "date": "2026-11-18",
        "area": "study",
        "proof": "Finished Unit 1 summary",
        "link": "https://example.org/proof-1",
    }


def test_log_ledger_appends_valid_row(home, capsys):
    rc = main([
        "--home", str(home), "log", "ledger",
        "--task", "T-261116-demo-cli",
        "--model", "codex",
        "--minutes", "25",
        "--note", "Reviewed test matrix, saved manual check",
        "--date", "2026-11-18",
    ])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out == '2026-11-18,T-261116-demo-cli,codex,25,"Reviewed test matrix, saved manual check"'
    with (home / "logs" / "ledger.csv").open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[-1] == ["2026-11-18", "T-261116-demo-cli", "codex", "25", "Reviewed test matrix, saved manual check"]


def test_log_health_creates_file_with_header_and_appends(home, capsys):
    health_csv = home / "logs" / "health.csv"
    assert not health_csv.exists()
    rc = main([
        "--home", str(home), "log", "health",
        "--sleep", "7.5",
        "--gym", "yes",
        "--energy", "4",
        "--note", "Steady morning run — Munchenpark",
        "--date", "2026-11-18",
    ])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "2026-11-18,7.5,yes,4,Steady morning run — Munchenpark"
    raw = health_csv.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in raw
    lines = raw.decode("utf-8").splitlines()
    assert lines[0] == "date,sleep_h,gym,energy_1_5,note"
    assert lines[1] == "2026-11-18,7.5,yes,4,Steady morning run — Munchenpark"


def test_log_hours_creates_file_with_header_and_supports_unicode(home, capsys):
    hours_csv = home / "logs" / "hours.csv"
    assert not hours_csv.exists()
    rc = main([
        "--home", str(home), "log", "hours",
        "--area", "german",
        "--hours", "1.5",
        "--note", "Hoerverstehen Uebung: Pruefungsteil 2 (ae/oe/ue -> äöüß)",
        "--date", "2026-11-18",
    ])
    assert rc == 0
    assert "äöüß" in capsys.readouterr().out
    with hours_csv.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows == [{
        "date": "2026-11-18",
        "area": "german",
        "hours": "1.5",
        "note": "Hoerverstehen Uebung: Pruefungsteil 2 (ae/oe/ue -> äöüß)",
    }]


def test_duplicate_last_line_is_refused(home, capsys):
    args = [
        "--home", str(home), "log", "hours",
        "--area", "study",
        "--hours", "2",
        "--note", "Software engineering slides",
        "--date", "2026-11-18",
    ]
    assert main(args) == 0
    capsys.readouterr()
    assert main(args) == 2
    assert "Duplicate row refused" in capsys.readouterr().err


def test_range_and_enum_validation(home):
    with pytest.raises(ValueError, match="sleep"):
        log.log_health(home, sleep=15, gym="yes", energy=3, date="2026-11-18")
    with pytest.raises(ValueError, match="sleep"):
        log.log_health(home, sleep=-1, gym="yes", energy=3, date="2026-11-18")
    with pytest.raises(ValueError, match="gym"):
        log.log_health(home, sleep=7, gym="maybe", energy=3, date="2026-11-18")
    with pytest.raises(ValueError, match="energy"):
        log.log_health(home, sleep=7, gym="no", energy=6, date="2026-11-18")
    with pytest.raises(ValueError, match="energy"):
        log.log_health(home, sleep=7, gym="no", energy=0, date="2026-11-18")
    with pytest.raises(ValueError, match="hours"):
        log.log_hours(home, area="study", hours=25, date="2026-11-18")
    with pytest.raises(ValueError, match="area"):
        log.log_hours(home, area="gaming", hours=2, date="2026-11-18")
    with pytest.raises(ValueError, match="minutes"):
        log.log_ledger(home, task="T-1", model="codex", minutes=-5, note="bad", date="2026-11-18")
    with pytest.raises(ValueError, match="date"):
        log.log_hours(home, area="study", hours=1, date="2026-99-99")
    with pytest.raises(ValueError, match="max 200"):
        log.log_hours(home, area="study", hours=1, note="x" * 201, date="2026-11-18")


def test_guard_refuses_secret_or_personal_text_and_names_rule(home):
    fake_iban = "DE89" + "370400440532013000"
    with pytest.raises(ValueError, match="IBAN"):
        log.log_hours(home, area="work", hours=1, note=f"Paid {fake_iban}", date="2026-11-18")


def test_missing_header_and_crlf_and_bom_are_repaired_safely(home):
    hours_csv = home / "logs" / "hours.csv"
    # Write a BOM + CRLF file missing the header row
    hours_csv.write_bytes(b"\xef\xbb\xbf2026-11-17,study,1.5,first entry\r\n")
    log.log_hours(home, area="lab", hours=2, note='quoted, "value"', date="2026-11-18")
    raw = hours_csv.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in raw
    with hours_csv.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["date", "area", "hours", "note"]
    assert rows[1] == ["2026-11-17", "study", "1.5", "first entry"]
    assert rows[2] == ["2026-11-18", "lab", "2", 'quoted, "value"']
