from lifeos import redact
from lifeos import guard
from lifeos.cli import main

KEY = "sk-ant-api03-" + "a1B2c3D4" * 5
IBAN = "DE89 3704 0044 0532 0130 00"  # lifeos-guard: allow (public example IBAN)
TEXT = f"plan for friday\nmy key {KEY}\nmail me at someone@example.org\npay to {IBAN}\nfine line\n"


def test_findings_lines_are_replaced_and_the_result_scans_clean():
    clean, n = redact.text(TEXT)
    assert n == 3 and guard.scan_text(clean) == []
    assert "plan for friday" in clean and "fine line" in clean
    assert KEY not in clean and "someone@" not in clean and "DE89" not in clean
    assert "[redacted: " in clean and clean.count("\n") == TEXT.count("\n")  # same line count


def test_clean_text_is_untouched():
    clean, n = redact.text("nothing here\nsecond line\n")
    assert (clean, n) == ("nothing here\nsecond line\n", 0)


def test_the_redacted_note_never_repeats_the_secret():
    clean, _ = redact.text(f"token = {KEY}")
    assert KEY[:10] not in clean


def test_cli_writes_copies_and_never_overwrites(tmp_path, capsys):
    src = tmp_path / "log.md"
    src.write_text(TEXT, encoding="utf-8")
    out = tmp_path / "out"
    assert main(["redact", str(src), "--out", str(out)]) == 0
    assert guard.scan_text((out / "log.md").read_text(encoding="utf-8")) == []
    assert src.read_text(encoding="utf-8") == TEXT  # original untouched
    assert main(["redact", str(src), "--out", str(out)]) == 2  # exists
