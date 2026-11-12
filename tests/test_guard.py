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


def test_staged_scan_reads_the_staged_version_not_the_working_file(tmp_path, monkeypatch):
    """Stage a token, then overwrite the file with clean text: the commit still carries the token."""
    if not shutil.which("git"):
        pytest.skip("git is not installed")
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    git("init", "-q")
    note = repo / "note.md"
    note.write_text("token " + "ghp_" + "a1" * 18 + "\n", encoding="utf-8")
    git("add", "note.md")
    note.write_text("clean now\n", encoding="utf-8")  # the working file no longer shows it
    monkeypatch.chdir(repo)
    assert main(["guard", "--staged"]) == 1


def test_guard_says_how_many_files_it_skipped(tmp_path, capsys):
    ok = tmp_path / "ok.md"
    ok.write_text("plain text\n", encoding="utf-8")
    binary = tmp_path / "bin.dat"
    binary.write_bytes(b"\0\xff\xfe")  # NUL and not valid UTF-8: a real binary
    assert main(["guard", str(ok), str(binary), str(tmp_path / "missing.md")]) == 0
    err = capsys.readouterr().err
    assert "1 file(s) checked" in err and "2 skipped" in err


def test_staged_scan_includes_renamed_files(tmp_path, monkeypatch):
    """A file renamed and edited in one commit shows up as R in git; it must still be scanned."""
    if not shutil.which("git"):
        pytest.skip("git is not installed")
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    git("init", "-q")
    (repo / "old.md").write_text("plain line one\nplain line two\nplain line three\n", encoding="utf-8")
    git("add", "old.md")
    git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "first")
    git("mv", "old.md", "new.md")
    (repo / "new.md").write_text("plain line one\nplain line two\nplain line three\ntoken " + "ghp_" + "a1" * 18 + "\n", encoding="utf-8")
    git("add", "new.md")
    monkeypatch.chdir(repo)
    assert main(["guard", "--staged"]) == 1


def test_private_patterns_file_with_a_bom_is_read(tmp_path, monkeypatch):
    from lifeos import guard
    patterns = tmp_path / "private-patterns.txt"
    patterns.write_bytes("﻿SecretCodename\n".encode("utf-8"))  # Notepad on Windows adds a BOM
    monkeypatch.setattr(guard, "PRIVATE_PATTERNS", patterns)
    assert ("BLOCK", "Private pattern") in kinds("the SecretCodename project", private=guard._private_patterns())


def test_a_bad_private_pattern_stops_the_guard_instead_of_being_ignored(tmp_path, monkeypatch, capsys):
    from lifeos import guard
    patterns = tmp_path / "private-patterns.txt"
    patterns.write_text("fine\n(unclosed\n", encoding="utf-8")
    monkeypatch.setattr(guard, "PRIVATE_PATTERNS", patterns)
    ok = tmp_path / "a.md"
    ok.write_text("text\n", encoding="utf-8")
    assert main(["guard", str(ok)]) != 0
    assert "private-patterns" in capsys.readouterr().err


def test_a_very_long_line_without_an_at_sign_is_scanned_fast():
    import time
    start = time.time()
    scan_text("a" * 60000)
    assert time.time() - start < 1.0  # the e-mail pattern was quadratic on such a line


def test_utf16_files_are_scanned_too(tmp_path):
    """PowerShell 5.1 writes UTF-16 with a BOM when you redirect with >."""
    path = tmp_path / "note.txt"
    path.write_bytes(("token " + "ghp_" + "a1" * 18 + "\n").encode("utf-16"))
    assert [p for p, _ in scan_paths([str(path)])] == [str(path)]


def test_a_utf16_private_patterns_file_is_read(tmp_path, monkeypatch):
    from lifeos import guard
    patterns = tmp_path / "private-patterns.txt"
    patterns.write_bytes("SecretCodename\n".encode("utf-16"))
    monkeypatch.setattr(guard, "PRIVATE_PATTERNS", patterns)
    assert ("BLOCK", "Private pattern") in kinds("the SecretCodename project", private=guard._private_patterns())
