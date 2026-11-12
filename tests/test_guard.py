import re
import shutil
import subprocess

import pytest

from lifeos.cli import main
from lifeos.guard import iban_valid, luhn_valid, scan_paths, scan_text

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


def test_staged_file_with_a_non_ascii_name_is_still_scanned(tmp_path, monkeypatch):
    """git prints Müller.md as "M\\303\\274ller.md"; the pre-commit guard must not skip it as a missing file."""
    if not shutil.which("git"):
        pytest.skip("git is not installed")
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    git("init", "-q")
    git("config", "core.quotepath", "true")  # git's default, pinned so a global setting cannot hide the problem
    (repo / "Müller.md").write_text("token " + "ghp_" + "a1" * 18 + "\n", encoding="utf-8")
    git("add", "--all")
    monkeypatch.chdir(repo)
    assert main(["guard", "--staged"]) == 1


def test_text_file_in_a_legacy_encoding_is_still_scanned(tmp_path):
    """A bank export saved by Excel is cp1252, not UTF-8. It must be scanned, not skipped like a binary file."""
    export = tmp_path / "export.csv"
    export.write_bytes(f"Empfänger;IBAN\nKöln GmbH;{IBAN}\n".encode("cp1252"))
    assert main(["guard", str(export)]) == 1
    binary = tmp_path / "scan.bin"
    binary.write_bytes(b"\x00\x01\xff\xfe" + IBAN.encode() + b"\x00")
    assert scan_paths([str(binary)]) == []  # real binary files are still skipped
