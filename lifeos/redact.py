"""`lifeos redact FILE... --out DIR`: write copies of files with every line the guard flags replaced by a note.

For sharing a log or a note: any line with a finding (a key, an IBAN, a card, an e-mail, a phone number, a private
pattern) becomes `[redacted: <kind>]`, so the line count stays the same and the secret is gone, not just masked. The
result is re-scanned and is clean by construction. Originals are never touched and copies are never overwritten.
"""
from pathlib import Path

from . import guard


class RedactError(Exception):
    pass


def text(content):
    private = guard.private_patterns()
    flagged = {}
    for number, _sev, kind, _masked in guard.scan_text(content, private):
        flagged.setdefault(number, kind)
    lines = content.splitlines(keepends=True)
    for number, kind in flagged.items():
        ending = lines[number - 1][len(lines[number - 1].rstrip("\r\n")):]
        lines[number - 1] = f"[redacted: {kind}]{ending}"
    return "".join(lines), len(flagged)


def copy(src, out):
    src, out = Path(src), Path(out)
    dest = out / src.name
    if dest.exists():
        raise RedactError(f"{dest} exists: copies are never overwritten.")
    try:
        content = src.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as err:
        raise RedactError(f"Cannot read {src} as text: {err}") from None
    clean, n = text(content)
    out.mkdir(parents=True, exist_ok=True)
    dest.write_text(clean, encoding="utf-8", newline="")
    return dest, n
