"""High-confidence privacy scanner for IDs, financial identifiers, keys and assigned secrets.

BLOCK findings fail the check (exit code 1); WARN findings are shown but pass.
Lines containing 'lifeos-guard: allow' are skipped. Extra private patterns (your street, your phone number)
live outside every repo in ~/.lifeos/private-patterns.txt, one regular expression per line.

This is a backstop, not a complete data-classification system: natural-language
medical, tenant or employer information still depends on the human policy.
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
    ("Basic authorization header", re.compile(r"(?i)\bauthorization\s*:\s*basic\s+[A-Za-z0-9+/=_-]{12,}")),
    ("Long key or secret value", re.compile(r"(?i)\b(?:key|secret|client_secret)\s*[:=]\s*[\x27\x22]?[A-Fa-f0-9]{32,}\b")),
    ("JSON web token", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("Social security number", re.compile(r"(?<![\d-])\d{3}-\d{2}-\d{4}(?![\d-])")),
]
ID_DOCUMENT = re.compile(
    r"(?i)\b(?:passport|reisepass|personalausweis|ausweis|aufenthaltstitel|residence permit|id card)"
    r"(?:\s*(?:no\.?|nr\.?|number|nummer))?\s*[:#]?\s*([A-Z0-9]{8,10})\b")
# A tax or social security number is only recognised after its label; a bare 11-digit number is too common to block.
TAX_ID = re.compile(r"(?i)\b(?:steuer-?id|steuer-?identifikationsnummer|steuernummer|tax id|social security number)\b"
                    r"\s*(?:no\.?|nr\.?|number|nummer)?\s*[:#=]?\s*([0-9][0-9 .-]{7,17}[0-9])")
# A PIN is only recognised when it is stated with a verb or a colon, never as a bare word before a number.
PIN = re.compile(r"(?i)\b(?:pin(?: code)?|geheimzahl)\b\s*(?:is|ist|=|:)\s*(\d{4,8})\b")
IBAN_CANDIDATE = re.compile(r"(?i)\b[A-Z]{2}\d{2}(?:[ .-]?[A-Z0-9]{4}){2,7}(?:[ .-]?[A-Z0-9]{1,3})?\b")
# A card number may end a sentence (a full stop after the last digit); a decimal point followed by a digit is still a number.
# Digits right after a run id prefix (R-261116-60279634) are an id, not a card, even if the checksum happens to pass.
CARD_CANDIDATE = re.compile(r"(?<!\w)(?<!\d\.)(?<!\bR-)(?:\d[ -]?){12,18}\d(?!\w|\.\d)")
CARD_DOTTED = re.compile(r"(?<!\w)(?<!\d\.)\d{4}(?:\.\d{4}){2,4}(?:\.\d{1,3})?(?!\w|\.\d)")
SECRET_ASSIGNMENT = re.compile(r"(?i)\b(?:password|passwort|api[_-]?key|secret|token)\b\s*[:=]\s*['\"]?[^\s'\"]{8,}")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
# A git diff header such as `index 1a2b3c4..5d6e7f8 100644` ends in a run of digits (object id, space, file mode) that can pass the
# card checksum by chance; it is never a card number.
DIFF_INDEX = re.compile(r"^\s*index [0-9a-f]{6,40}\.\.[0-9a-f]{6,40}(?: [0-7]{6})?\s*$")
PHONE = re.compile(r"(?<!\w)\+\d{2,3}[ \-]?\d{2,4}[ \-]?\d{3,}[ \-]?\d{0,6}")


def iban_valid(text):
    raw = re.sub(r"[ .-]", "", text).upper()
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


def private_patterns():
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


def scan_text(text, private=(), allow_mark=True):
    """Return findings as (line_number, severity, kind, masked_excerpt)."""
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        if allow_mark and ALLOW_MARK in line:
            continue
        for kind, pattern in TOKEN_PATTERNS:
            for m in pattern.finditer(line):
                findings.append((number, "BLOCK", kind, _mask(m.group(0))))
        for m in ID_DOCUMENT.finditer(line):
            if any(c.isdigit() for c in m.group(1)):
                findings.append((number, "BLOCK", "ID or passport number", _mask(m.group(1))))
        for m in TAX_ID.finditer(line):
            if sum(c.isdigit() for c in m.group(1)) >= 9:
                findings.append((number, "BLOCK", "Tax or social security number", _mask(m.group(1))))
        for m in PIN.finditer(line):
            findings.append((number, "BLOCK", "PIN", _mask(m.group(1))))
        for m in IBAN_CANDIDATE.finditer(line):
            if iban_valid(m.group(0)):
                findings.append((number, "BLOCK", "IBAN", _mask(m.group(0))))
        for pattern in (() if DIFF_INDEX.match(line) else (CARD_CANDIDATE, CARD_DOTTED)):
            for m in pattern.finditer(line):
                if luhn_valid(m.group(0)):
                    findings.append((number, "BLOCK", "Card number", _mask(m.group(0))))
        for pattern in private:
            for m in pattern.finditer(line):
                findings.append((number, "BLOCK", "Private pattern", _mask(m.group(0))))
        for m in SECRET_ASSIGNMENT.finditer(line):
            findings.append((number, "BLOCK", "Assigned secret", _mask(m.group(0))))
        for m in EMAIL.finditer(line):
            findings.append((number, "WARN", "Email address", _mask(m.group(0))))
        for m in PHONE.finditer(line):
            findings.append((number, "WARN", "Phone number", _mask(m.group(0))))
    findings += _split_tokens(text, allow_mark)
    return findings


def _split_tokens(text, allow_mark):
    """A token wrapped over two lines by an editor or a chat: join each pair of adjacent non-blank lines and keep only the
    matches that cross the line break (a token on one line is already reported by the line scan)."""
    lines = text.splitlines()
    found = []
    for index in range(len(lines) - 1):
        first, second = lines[index].rstrip(), lines[index + 1].lstrip()
        if not first or not second or (allow_mark and (ALLOW_MARK in first or ALLOW_MARK in second)):
            continue
        joined = first + second
        for kind, pattern in TOKEN_PATTERNS:
            for m in pattern.finditer(joined):
                if m.start() < len(first) < m.end():
                    found.append((index + 1, "BLOCK", kind, _mask(m.group(0))))
                    found.append((index + 2, "BLOCK", kind, _mask(m.group(0))))  # both halves, so `redact` removes both lines
    return found


def staged_files():
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"],  # -z: names are not C-quoted
                         capture_output=True, encoding="utf-8", errors="surrogateescape", check=True).stdout
    return [name for name in out.split("\0") if name]


def scan_paths(paths, skipped=None):
    """Scan text files; return (path, findings) pairs for files with findings. Skipped names go into `skipped`."""
    private = private_patterns()
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
    private = private_patterns()
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

