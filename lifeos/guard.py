"""Privacy guard: stops class C data (IDs, bank and card numbers, keys, passwords) before it reaches a repo.

BLOCK findings fail the check (exit code 1); WARN findings are shown but pass.
Lines containing 'lifeos-guard: allow' are skipped. Extra private patterns (your street, your phone number)
live outside every repo in ~/.lifeos/private-patterns.txt, one regular expression per line.
"""
import re
import subprocess
from pathlib import Path

ALLOW_MARK = "lifeos-guard: allow"
PRIVATE_PATTERNS = Path("~/.lifeos/private-patterns.txt").expanduser()
MAX_BYTES = 1_000_000

TOKEN_PATTERNS = [
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{40,}")),
    ("API key (sk-)", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_\-]{24,}")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("Private key", re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----")),
]
ID_DOCUMENT = re.compile(
    r"(?i)\b(?:passport|reisepass|personalausweis|ausweis|aufenthaltstitel|residence permit|id card)"
    r"(?:\s*(?:no\.?|nr\.?|number|nummer))?\s*[:#]?\s*([A-Z0-9]{8,10})\b")
IBAN_CANDIDATE = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b")
CARD_CANDIDATE = re.compile(r"(?<![\d.])(?:\d[ -]?){12,18}\d(?![\d.])")
SECRET_ASSIGNMENT = re.compile(r"(?i)\b(?:password|passwort|api[_-]?key|secret|token)\b\s*[:=]\s*['\"]?[^\s'\"]{8,}")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
PHONE = re.compile(r"(?<!\w)\+\d{2,3}[ \-]?\d{2,4}[ \-]?\d{3,}[ \-]?\d{0,6}")


def iban_valid(text):
    raw = text.replace(" ", "")
    if not 15 <= len(raw) <= 34:
        return False
    moved = raw[4:] + raw[:4]
    digits = "".join(str(int(c, 36)) for c in moved)
    return int(digits) % 97 == 1


def luhn_valid(text):
    digits = [int(c) for c in text if c.isdigit()]
    if not 13 <= len(digits) <= 19 or len(set(digits)) == 1:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def _mask(value):
    value = value.strip()
    return value[:4] + "…" if len(value) > 4 else "…"


def _decode(raw):
    """Text of a file's bytes, or None for a real binary. UTF-16 with a BOM (PowerShell's > redirect) is text too."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return raw.decode("utf-16")
        except UnicodeDecodeError:
            return None
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:  # cp1252/latin-1 text (an Excel CSV) is scanned; only files with NUL bytes are binary
        return None if b"\0" in raw else raw.decode("latin-1")


def _private_patterns():
    if not PRIVATE_PATTERNS.exists():
        return []
    patterns = []
    for number, line in enumerate((_decode(PRIVATE_PATTERNS.read_bytes()) or "").splitlines(), 1):  # BOM and UTF-16 safe
        line = line.strip()
        if line and not line.startswith("#"):
            try:
                patterns.append(re.compile(line, re.I))
            except re.error as error:  # fail closed: a pattern that silently does nothing would hide a leak
                raise ValueError(f"private-patterns file {PRIVATE_PATTERNS}, line {number}: bad pattern ({error})") from error
    return patterns


def scan_text(text, private=()):
    """Return findings as (line_number, severity, kind, masked_excerpt)."""
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        if ALLOW_MARK in line:
            continue
        for kind, pattern in TOKEN_PATTERNS:
            for m in pattern.finditer(line):
                findings.append((number, "BLOCK", kind, _mask(m.group(0))))
        for m in ID_DOCUMENT.finditer(line):
            if any(c.isdigit() for c in m.group(1)):
                findings.append((number, "BLOCK", "ID or passport number", _mask(m.group(1))))
        for m in IBAN_CANDIDATE.finditer(line):
            if iban_valid(m.group(0)):
                findings.append((number, "BLOCK", "IBAN", _mask(m.group(0))))
        for m in CARD_CANDIDATE.finditer(line):
            if luhn_valid(m.group(0)):
                findings.append((number, "BLOCK", "Card number", _mask(m.group(0))))
        for pattern in private:
            for m in pattern.finditer(line):
                findings.append((number, "BLOCK", "Private pattern", _mask(m.group(0))))
        for m in SECRET_ASSIGNMENT.finditer(line):
            findings.append((number, "WARN", "Possible secret", _mask(m.group(0))))
        for m in EMAIL.finditer(line):
            findings.append((number, "WARN", "Email address", _mask(m.group(0))))
        for m in PHONE.finditer(line):
            findings.append((number, "WARN", "Phone number", _mask(m.group(0))))
    return findings


def staged_files():
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"],  # -z: names are not C-quoted
                         capture_output=True, encoding="utf-8", errors="surrogateescape", check=True).stdout
    return [name for name in out.split("\0") if name]


def scan_paths(paths, skipped=None):
    """Scan text files; return (path, findings) pairs for files with findings. Skipped names go into `skipped`."""
    private = _private_patterns()
    results = []
    for name in paths:
        path = Path(name)
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            if skipped is not None:
                skipped.append(name)
            continue
        try:
            text = _decode(path.read_bytes())
        except OSError:
            text = None
        if text is None:
            if skipped is not None:
                skipped.append(name)
            continue
        findings = scan_text(text, private)
        if findings:
            results.append((str(path), findings))
    return results


def scan_staged(names, skipped=None):
    """Scan what is staged (the version a commit would carry), not the working file, which may differ."""
    private = _private_patterns()
    results = []
    for name in names:
        proc = subprocess.run(["git", "show", f":{name}"], capture_output=True)
        raw = proc.stdout
        text = None if proc.returncode or len(raw) > MAX_BYTES else _decode(raw)
        if text is None:
            if skipped is not None:
                skipped.append(name)
            continue
        findings = scan_text(text, private)
        if findings:
            results.append((name, findings))
    return results
