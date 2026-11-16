"""One seat table for every model LifeOS can call.

A seat is a model plus what it is good at, whether it leaves the laptop, and how
much of the weekly cloud budget it may spend. `choose` returns the first open
seat and the seats that may replace it. Private and sensitive work never gains
a cloud seat. A usage-limit failure rests that seat so the next task does not
spend a call on a provider that will only refuse.
"""
import datetime as dt
import re

LOCAL = frozenset({"ollama", "qwen"})
REMOTE = frozenset({"claude", "codex", "gemini"})

# Context tokens and calls a remote seat may spend in SEVEN_DAYS. Local seats
# have no cloud share. The numbers leave headroom under the router's 120_000
# token and 80 call week so one provider is not the one that runs out.
SHARES = {"claude": 40_000, "codex": 40_000, "gemini": 30_000}
CALL_CAP = 24
SEVEN_DAYS = 7
REST_HOURS = 12

# First match wins. Local work is first so "private" beats "python".
# Levels match the recorded split: Claude writes code (D23), Codex checks,
# Gemini reads, Qwen stays on the laptop.
KINDS = [
    ("qwen", "none", "L1",
     "private sorting, extraction and other small jobs stay on this laptop (Qwen)",
     r"private|local(?:ly)?|csv|sort|classify|categori[sz]e|rename|tidy|offline|extract|checklist|reformat"),
    ("gemini", "claude", "L1",
     "long reading and live facts go to Gemini; Grok is not a seat yet",
     r"price|news|latest|today|job posting|long|pdf|paper|research|summari[sz]e|bulk|read all"),
    ("codex", "claude", "L0",
     "tests, reviews, German and exams go to the ChatGPT seat (Codex)",
     r"bug|test|pytest|review|adversarial|ship|merge|command|german|exam|quiz|learn|teach|vocabulary"),
    ("claude", "codex", "L2",
     "Claude writes the code; Codex is the check seat",
     r"code|implement|refactor|script|python|function|module|cli|\.py\b|\.js\b|\.ts\b"),
    ("claude", "codex", "L3",
     "plans, decisions and writing stay with Claude",
     r"plan|write|draft|decide|decision|memo|strategy|email|permit|contract|buy|subscription"),
]
DEFAULT = ("claude", "codex", "L2", "no clear kind of work, so Claude takes it and Codex can check")

# Replacement order. A local seat has no cloud seat after it.
CHAINS = {
    "qwen": ["qwen", "ollama"],
    "ollama": ["ollama"],
    "claude": ["claude", "codex", "gemini", "qwen", "ollama"],
    "codex": ["codex", "claude", "gemini", "qwen", "ollama"],
    "gemini": ["gemini", "claude", "codex", "qwen", "ollama"],
}

GOOD_AT = {
    "qwen": "small local jobs and anything that must stay on this laptop",
    "ollama": "the other local model, used only when Qwen is down",
    "claude": "plans, decisions, writing and the code draft",
    "codex": "tests, bugs, review, German and exams",
    "gemini": "long reading, research and live facts",
}

_QUOTA = ("usage limit", "rate limit", "quota", "too many requests", "insufficient_quota")
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_RESET = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})"
    r"(?:\s+(\d{1,2}):(\d{2})\s*([ap]m))?",
    re.I,
)
_ISO = re.compile(r"\b(20\d{2}-\d{2}-\d{2})(?:[T ](\d{2}):(\d{2}))?")
_SPENDS = frozenset({"ok", "failed", "timeout", "partial"})


def seat_name(label):
    """Return the seat id for a run label such as 'qwen:qwen3.5:4b'."""
    name = str(label or "").split(":", 1)[0].strip().lower()
    return name if name in CHAINS else ""


def kind(text):
    """Return (model, reviewer, level, reason) for the task text."""
    for model, reviewer, level, reason, words in KINDS:
        if re.search(rf"(?<![a-z])({words})", text or "", re.I):
            return model, reviewer, level, reason
    return DEFAULT


def pick(text):
    """Return (model, reason). The reviewer and level stay with `kind`."""
    model, _reviewer, _level, reason = kind(text)
    return model, reason


def failure_kind(message):
    """Classify a provider error so the route note can name it in one word."""
    text = str(message or "").lower()
    if "timed out" in text or "timeout" in text or "did not answer within" in text:
        return "timeout"
    if any(phrase in text for phrase in _QUOTA):
        return "usage_limit"
    if any(phrase in text for phrase in ("not installed", "not on path", "not reachable", "no model")):
        return "missing"
    return "failed"


def brief(message, limit=160):
    """One short line of an error, safe to put in a task file."""
    text = " ".join(str(message or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def focus_error(message):
    """Keep the sentence that says why a call failed when a banner comes first."""
    text = str(message or "")
    low = text.lower()
    markers = _QUOTA + ("try again", "timed out", "not installed", "not on path", "not reachable")
    for marker in markers:
        at = low.find(marker)
        if at != -1:
            start = max(0, at - 48)
            return text[start:].strip()
    return text


def _aware(moment):
    if moment.tzinfo is None:
        return moment.replace(tzinfo=dt.timezone.utc)
    return moment.astimezone(dt.timezone.utc)


def _parse_reset(message):
    """Return a UTC time named in a provider error, or None.

    The provider often omits the timezone. The clock is stored as UTC and the
    route note says so.
    """
    named = _RESET.search(message or "")
    if named:
        hour, minute = 0, 0
        if named.group(4):
            hour = int(named.group(4)) % 12
            minute = int(named.group(5))
            if named.group(6).lower() == "pm":
                hour += 12
        return dt.datetime(
            int(named.group(3)), _MONTHS[named.group(1).lower()[:3]], int(named.group(2)),
            hour, minute, tzinfo=dt.timezone.utc,
        )
    iso = _ISO.search(message or "")
    if not iso:
        return None
    hour = int(iso.group(2) or 0)
    minute = int(iso.group(3) or 0)
    year, month, day = (int(part) for part in iso.group(1).split("-"))
    return dt.datetime(year, month, day, hour, minute, tzinfo=dt.timezone.utc)


def _finished(record):
    raw = str(record.get("finished_at") or record.get("started_at") or "")
    if not raw:
        return None
    try:
        return _aware(dt.datetime.fromisoformat(raw.replace("Z", "+00:00")))
    except ValueError:
        return None


def pressure(records, now):
    """Return {seat: reason} for seats that should not be called.

    A usage-limit failure rests the seat until the time in the message, or for
    REST_HOURS when the message has no time. A later ok run clears the rest.
    Remote seats also rest when they have spent their 7-day share or call cap.
    """
    now = _aware(now)
    window = (now.date() - dt.timedelta(days=SEVEN_DAYS)).isoformat()
    newest = {}
    tokens = {}
    calls = {}
    for rec in records or []:
        if rec.get("command") not in ("ask", "review"):
            continue
        seat = seat_name(rec.get("model"))
        if not seat:
            continue
        day = str(rec.get("date") or "")[:10]
        if day and day < window:
            continue
        stamp = rec.get("finished_at") or rec.get("started_at") or ""
        prev = newest.get(seat)
        if prev is None or stamp >= prev[0]:
            newest[seat] = (stamp, rec)
        if rec.get("status") in _SPENDS and seat in SHARES:
            amount = rec.get("tokens")
            if isinstance(amount, int) and not isinstance(amount, bool):
                tokens[seat] = tokens.get(seat, 0) + amount
            calls[seat] = calls.get(seat, 0) + 1
    resting = {}
    for seat, (_stamp, rec) in newest.items():
        if rec.get("status") not in ("failed", "timeout"):
            continue
        if failure_kind(rec.get("error")) != "usage_limit":
            continue
        until = _parse_reset(rec.get("error") or "")
        if until is None:
            finished = _finished(rec)
            until = finished + dt.timedelta(hours=REST_HOURS) if finished else None
        if until is not None and now < until:
            resting[seat] = f"usage limit until {until:%Y-%m-%d %H:%M} UTC"
    for seat, share in SHARES.items():
        if seat in resting:
            continue
        used = tokens.get(seat, 0)
        made = calls.get(seat, 0)
        if used >= share:
            resting[seat] = f"over its {share} context-token share ({used} in {SEVEN_DAYS} days)"
        elif made >= CALL_CAP:
            resting[seat] = f"over its {CALL_CAP} call cap ({made} in {SEVEN_DAYS} days)"
    return resting


def _local_only(model, tier):
    return tier in ("SENSITIVE", "SECRET") or model in LOCAL


def order(model, tier, pressure_map, explicit=False):
    """Return the seats to try, best first.

    An explicit cloud seat is tried even when it is resting: the owner asked
    for it. Every later seat that is resting is skipped. Sensitive work and a
    local primary never gain a cloud seat. When every cloud seat is resting,
    the local seats take the job.
    """
    if model not in CHAINS:
        raise ValueError(f"Unknown model '{model}'. Choose one of: {', '.join(sorted(CHAINS))}.")
    if _local_only(model, tier):
        chain = ["ollama"] if model == "ollama" else ["qwen", "ollama"]
    else:
        chain = list(CHAINS[model])
    blocked = pressure_map or {}
    if explicit and not _local_only(model, tier):
        return [chain[0]] + [name for name in chain[1:] if name not in blocked]
    open_seats = [name for name in chain if name not in blocked]
    if open_seats:
        return open_seats
    if not _local_only(model, tier):
        return ["qwen", "ollama"]
    return chain


def choose(text, tier, pressure_map, explicit=None):
    """Return (model, reason, chain) for this task and the seats already resting."""
    if explicit:
        primary, reason = explicit, "chosen by you"
    else:
        primary, _reviewer, _level, reason = kind(text)
    if tier in ("SENSITIVE", "SECRET"):
        primary = "ollama" if explicit == "ollama" else "qwen"
        reason = "SENSITIVE data stays on this laptop (Qwen, then Ollama)"
        if tier == "SECRET":
            reason = "SECRET data cannot be sent; the call stops before any model"
    chain = order(primary, tier, pressure_map, explicit=bool(explicit))
    skipped = []
    raw = ["ollama"] if primary == "ollama" else (
        ["qwen", "ollama"] if _local_only(primary, tier) else list(CHAINS.get(primary, []))
    )
    for name in raw:
        if name not in chain and name in (pressure_map or {}):
            skipped.append(f"skipped {name}: {pressure_map[name]}")
    if chain and chain[0] != primary:
        skipped.append(f"starting with {chain[0]} ({GOOD_AT.get(chain[0], chain[0])})")
    if skipped:
        reason = reason + " · " + " · ".join(skipped)
    return (chain[0] if chain else primary), reason, chain
