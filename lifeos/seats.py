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
REMOTE = frozenset({"claude", "codex", "gemini", "grok"})

# Context tokens and calls a remote seat may spend in SEVEN_DAYS. Local seats
# have no cloud share. The numbers leave headroom under the router's 120_000
# token and 80 call week so one provider is not the one that runs out.
SHARES = {"claude": 40_000, "codex": 40_000, "gemini": 30_000, "grok": 20_000}
CALL_CAP = 24
WEEKLY_TOKENS = 120_000  # all cloud seats together: the one weekly ruler
WEEKLY_CALLS = 80
SEVEN_DAYS = 7
REST_HOURS = 12

# First match wins. Local work is first so "private" beats "python".
# Levels match the recorded split: Claude writes code, Codex checks,
# Gemini reads, Qwen stays on the laptop.
KINDS = [
    ("qwen", "none", "L1",
     "private sorting, extraction and other small jobs stay on this laptop (Qwen)",
     r"private|local(?:ly)?|csv|sort|classify|categori[sz]e|rename|tidy|offline|extract|checklist|reformat"),
    ("grok", "claude", "L1",
     "live facts (prices, news, today) go to the locked Grok seat; answers need a source and a date",
     r"price|news|latest|today|job posting|right now|current"),
    ("gemini", "claude", "L1",
     "long reading and research go to Gemini",
     r"long|pdf|paper|research|summari[sz]e|bulk|read all"),
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
    "grok": ["grok", "gemini", "claude", "codex", "qwen", "ollama"],  # live facts only; no other seat falls back to it
}

GOOD_AT = {
    "qwen": "small local jobs and anything that must stay on this laptop",
    "ollama": "the other local model, used only when Qwen is down",
    "claude": "plans, decisions, writing and the code draft",
    "codex": "tests, bugs, review, German and exams",
    "gemini": "long reading and research",
    "grok": "live facts with a source and a date; locked: no plan mode, no subagents, tools refused",
}

_QUOTA = ("usage limit", "rate limit", "quota", "too many requests", "insufficient_quota")
_NO_CREDITS = ("out of credits", "no credits", "insufficient credits", "http 402", "402 payment required")
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
_AFTER = re.compile(r"(?:resets?|try again|available|retry)\s+in\s+((?:\d+\s*[a-z]+[\s,]*(?:and\s+)?){1,4})", re.I)
_PART = re.compile(r"(\d+)\s*(days?|d|hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)(?![a-z])", re.I)
_UNIT = {"d": 86400, "h": 3600, "m": 60, "s": 1}
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


SHOP = r"price|prices|cheapest|in stock|availability|buy\b|shop|offer"
LIVE = r"latest|news|today|current|right now|price|prices|weather|score"
# What a seat has no tool for, as a hint before the call (never a block). Found in the first week of real use.
CANNOT = {
    "grok": [
        (rf"\b({SHOP})", "grok cannot read shop or price-comparison sites (they block automated fetches, live check "
                          "2026-11-26). Name pages that allow it, or look it up yourself."),
        (r"\b(edit|modify|rename|commit|create a file|write to|save to)\b", "grok has no tools for files (only web_fetch): "
                          "it can answer in the reply, not change or save anything."),
        (r"http://|https?://(?:localhost|127\.|10\.|192\.168\.|172\.(?:1[6-9]|2[0-9]|3[01])\.)", "grok can only fetch public https pages: a plain http or private address will not work and should not be sent."),
        (r"\b(run|execute)\b.{0,30}\b(test|tests|suite|command|script)", "grok has no shell (only web_fetch): "
                          "it cannot run anything."),
    ],
    "qwen": [(rf"\b({LIVE})\b", "qwen runs on this laptop with no web access: a live fact needs grok, with public questions only.")],
    "ollama": [(rf"\b({LIVE})\b", "ollama runs on this laptop with no web access: a live fact needs grok, with public questions only.")],
}


# The same limits as `CANNOT`, as a plain table for the cockpit: which of four jobs a seat has no tool for. A test keeps the two
# in step (every seat in CANNOT has a row here and the other way round).
BLOCKS = {"grok": ("shop", "files", "shell"), "qwen": ("web", "shop"), "ollama": ("web", "shop")}
JOBS = {
    "claude": "Lead seat: plans, checks, writes the final call",
    "codex": "Code review and small fixes",
    "gemini": "Long reading, summaries and quote checks",
    "grok": "Public web pages (one fetch tool)",
    "qwen": "Private work that must stay on this laptop",
    "ollama": "Small private jobs, offline",
}
NOTES = {
    "grok": "Shop and price sites, saving files, running commands, plain http",
    "qwen": "Live web facts; slow on this CPU until the RAM goes in",
    "ollama": "Live web facts; gave a placeholder once",
}


def capability_rows():
    """One dict per seat for the cockpit: seat, kind, job, what it cannot do, and web/shop/files/shell as 'ok' or 'blocked'."""
    rows = []
    for seat in ("claude", "codex", "gemini", "grok", "qwen", "ollama"):
        blocked = BLOCKS.get(seat, ())
        rows.append({"seat": seat, "kind": "local" if seat in LOCAL else "cloud", "job": JOBS[seat],
                     "cannot": NOTES.get(seat, "Nothing blocked in the seat table"),
                     **{job: "blocked" if job in blocked else "ok" for job in ("web", "shop", "files", "shell")}})
    return rows


def seat_warning(model, text):
    """A hint, never a block: the first thing in the task this seat has no tool for."""
    for pattern, message in CANNOT.get(model, []):
        if re.search(pattern, text or "", re.I):
            return message
    return ""


def reroute(chain, text):
    """Put the seats that have a tool for the job ahead of those that do not (`CANNOT`), keeping each group's order.
    Returns (chain, note). The chain is unchanged when the first seat can do the job, when no seat can, or when it has one
    seat. Nothing is added or dropped, so a private chain stays private."""
    if len(chain) < 2:
        return list(chain), ""
    capable = [s for s in chain if not seat_warning(s, text)]
    incapable = [s for s in chain if seat_warning(s, text)]
    if not capable or not incapable or chain[0] in capable:
        return list(chain), ""
    return capable + incapable, f"{chain[0]} has no tool for this job, so {capable[0]} goes first"


def pick(text):
    """Return (model, reason). The reviewer and level stay with `kind`."""
    model, _reviewer, _level, reason = kind(text)
    return model, reason


def failure_kind(message):
    """Classify a provider error so the route note can name it in one word."""
    text = str(message or "").lower()
    if "timed out" in text or "timeout" in text or "did not answer within" in text:
        return "timeout"
    if any(phrase in text for phrase in _NO_CREDITS):
        return "no_credits"
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
    markers = _NO_CREDITS + _QUOTA + ("try again", "timed out", "not installed", "not on path", "not reachable")
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


_ZONE = re.compile(
    r"^\s*(?:(?:utc|gmt)\s*([+-]\d{1,2})(?::?(\d{2}))?|(utc|gmt|z)\b|([+-])(\d{2}):?(\d{2}))", re.I
)
REST_CEILING_DAYS = 8


def _zone(tail):
    """Return (offset, True) when the text after a clock names a timezone, else (None, False)."""
    found = _ZONE.match(tail or "")
    if not found:
        return None, False
    if found.group(3):
        return dt.timedelta(0), True
    if found.group(1):
        hours = int(found.group(1))
        minutes = int(found.group(2) or 0)
        sign = -1 if found.group(1).startswith("-") else 1
        return dt.timedelta(hours=hours, minutes=sign * minutes), True
    sign = -1 if found.group(4) == "-" else 1
    return sign * dt.timedelta(hours=int(found.group(5)), minutes=int(found.group(6))), True


def _parse_reset(message):
    """Return (UTC time, timezone_was_given) named in a provider error, or (None, False).

    A clock with an explicit zone (UTC, GMT, Z, +01:00, UTC+1) is converted to
    UTC. A clock without one is read as UTC and the caller flags that.
    """
    message = message or ""
    named = _RESET.search(message)
    if named:
        hour, minute = 0, 0
        if named.group(4):
            hour = int(named.group(4)) % 12
            minute = int(named.group(5))
            if named.group(6).lower() == "pm":
                hour += 12
        moment = dt.datetime(
            int(named.group(3)), _MONTHS[named.group(1).lower()[:3]], int(named.group(2)),
            hour, minute, tzinfo=dt.timezone.utc,
        )
        offset, given = _zone(message[named.end():named.end() + 12]) if named.group(4) else (None, False)
        return (moment - offset if given else moment), given
    iso = _ISO.search(message)
    if not iso:
        return None, False
    hour = int(iso.group(2) or 0)
    minute = int(iso.group(3) or 0)
    year, month, day = (int(part) for part in iso.group(1).split("-"))
    moment = dt.datetime(year, month, day, hour, minute, tzinfo=dt.timezone.utc)
    offset, given = _zone(message[iso.end():iso.end() + 16].lstrip(":0123456789.")) if iso.group(2) else (None, False)
    return (moment - offset if given else moment), given


def _parse_relative(message):
    """Return the wait named as a duration ('Resets in 78h40m32s', 'try again in 45 minutes'), or None."""
    found = _AFTER.search(message or "")
    if not found:
        return None
    parts = _PART.findall(found.group(1))
    if not parts:
        return None
    seconds = sum(int(number) * _UNIT[unit[0].lower()] for number, unit in parts)
    return dt.timedelta(seconds=seconds)


def _rest_until(record):
    """Return (until, note) for a usage-limit failure. The note flags anything guessed."""
    finished = _finished(record)
    parsed, given = _parse_reset(record.get("error") or "")
    fallback = finished + dt.timedelta(hours=REST_HOURS) if finished else None
    wait = _parse_relative(record.get("error") or "") if parsed is None else None
    if wait is not None and finished is not None:
        if wait <= dt.timedelta(0):
            return fallback, "reset wait was zero, 12 h rest"
        if wait > dt.timedelta(days=REST_CEILING_DAYS):
            return finished + dt.timedelta(days=REST_CEILING_DAYS), f"reset time was over {REST_CEILING_DAYS} days away, capped"
        return finished + wait, ""
    if parsed is None:
        return fallback, "no time in the message, 12 h rest"
    if finished is not None and parsed <= finished:
        return fallback, "reset time was before the failure, 12 h rest"
    if finished is not None and parsed > finished + dt.timedelta(days=REST_CEILING_DAYS):
        return finished + dt.timedelta(days=REST_CEILING_DAYS), f"reset time was over {REST_CEILING_DAYS} days away, capped"
    return parsed, "" if given else "no timezone given, read as UTC"


def _finished(record):
    raw = str(record.get("finished_at") or record.get("started_at") or "")
    if not raw:
        return None
    try:
        return _aware(dt.datetime.fromisoformat(raw.replace("Z", "+00:00")))
    except ValueError:
        return None


def _spend(records, now):
    """Return (newest ask/review/smoke record per seat, tokens per cloud seat, calls per cloud seat) for 7 days."""
    window = (_aware(now).date() - dt.timedelta(days=SEVEN_DAYS)).isoformat()
    newest, tokens, calls = {}, {}, {}
    for rec in records or []:
        if rec.get("command") not in ("ask", "review", "smoke", "debate"):
            continue
        if rec.get("command") == "debate" and rec.get("source") == "manual":
            continue  # a pasted answer is not a call this machine made
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
        if rec.get("command") != "smoke" and rec.get("status") in _SPENDS and seat in SHARES:
            amount = rec.get("tokens")
            if isinstance(amount, int) and not isinstance(amount, bool):
                tokens[seat] = tokens.get(seat, 0) + amount
            calls[seat] = calls.get(seat, 0) + 1
    return newest, tokens, calls


def _last_good_days(records, now):
    """Days since each seat's newest real successful call, across the full ledger."""
    ages = {}
    for rec in records or []:
        if (rec.get("status") != "ok" or rec.get("command") not in ("ask", "review", "smoke", "debate")
                or (rec.get("command") == "debate" and rec.get("source") == "manual")):
            continue
        seat = seat_name(rec.get("model"))
        if not seat:
            continue
        finished = _finished(rec)
        try:
            day = finished.date() if finished else dt.date.fromisoformat(str(rec.get("date") or "")[:10])
        except ValueError:
            continue
        age = max(0, (_aware(now).date() - day).days)
        ages[seat] = min(ages.get(seat, age), age)
    return ages


def budget(records, now):
    """The one cloud budget. A seat's limit is the lower of its share and what the week has left."""
    _newest, tokens, calls = _spend(records, now)
    total, made = sum(tokens.values()), sum(calls.values())
    plan = {"cap_tokens": WEEKLY_TOKENS, "cap_calls": WEEKLY_CALLS, "used_tokens": total, "used_calls": made, "seats": {}}
    for seat, share in SHARES.items():
        others = total - tokens.get(seat, 0)
        plan["seats"][seat] = {
            "used": tokens.get(seat, 0), "calls": calls.get(seat, 0),
            "share": share, "limit": max(0, min(share, WEEKLY_TOKENS - others)),
        }
    return plan


def pressure(records, now):
    """Return {seat: reason} for seats that should not be called.

    An out-of-credits failure rests the seat until a later successful call.
    A usage-limit failure rests the seat until the time in the message (see
    `_rest_until` for the floor, ceiling and timezone rules). A later ok run
    clears the rest. Cloud seats also rest on the one budget: their own 7-day
    token share or call cap, the weekly cap for all cloud seats together, or
    the weekly call cap.
    """
    now = _aware(now)
    newest, _tokens, _calls = _spend(records, now)
    plan = budget(records, now)
    resting = {}
    for seat, (_stamp, rec) in newest.items():
        if rec.get("status") not in ("failed", "timeout"):
            continue
        kind = failure_kind(rec.get("error"))
        if kind == "no_credits":
            resting[seat] = "out of credits; add credits before retrying"
            continue
        if kind != "usage_limit":
            continue
        until, note = _rest_until(rec)
        if until is not None and now < until:
            resting[seat] = f"usage limit until {until:%Y-%m-%d %H:%M} UTC" + (f" ({note})" if note else "")
    for seat, info in plan["seats"].items():
        if seat in resting:
            continue
        if info["used"] >= info["limit"] and info["used"] > 0 or info["limit"] == 0:
            if info["limit"] < info["share"]:
                resting[seat] = (f"over the weekly cloud cap ({plan['used_tokens']} of {plan['cap_tokens']} "
                                 f"tokens in {SEVEN_DAYS} days)")
            else:
                resting[seat] = f"over its {info['share']} context-token share ({info['used']} in {SEVEN_DAYS} days)"
        elif plan["used_calls"] >= plan["cap_calls"]:
            resting[seat] = f"over the weekly cloud call cap ({plan['used_calls']} of {plan['cap_calls']} in {SEVEN_DAYS} days)"
        elif info["calls"] >= CALL_CAP:
            resting[seat] = f"over its {CALL_CAP} call cap ({info['calls']} in {SEVEN_DAYS} days)"
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


def notes(text, tier, answered, pressure_map, explicit=None, available=None):
    """Honest flags for an answer that came from a replacement seat.

    degraded: a small local model answered where a cloud seat was meant to.
    check pending: the seat that checks risky work is resting, missing, or is
    the seat that wrote it, so the check has not happened. Nothing is skipped
    in silence.
    """
    wanted, reviewer, level, _reason = kind(text)
    if explicit:
        wanted = explicit
    out = []
    if tier not in ("SENSITIVE", "SECRET") and wanted in REMOTE and answered in LOCAL:
        out.append(
            f"degraded: {answered} (a small local model) answered in place of {wanted}; "
            "read it as a draft and have it checked"
        )
    if level in ("L2", "L3") and reviewer != "none" and tier not in ("SENSITIVE", "SECRET"):
        if reviewer == answered:
            out.append(f"check pending: {answered} wrote it and cannot check its own work; ask {_other(answered)} to review")
        elif reviewer in (pressure_map or {}):
            out.append(f"check pending: {reviewer} is resting ({pressure_map[reviewer]}); run the review when it is open")
        elif available is not None and reviewer not in available:
            out.append(f"check pending: {reviewer} is not available on this computer; run the review elsewhere")
    return out


def _other(seat):
    return next((name for name in ("codex", "claude", "gemini") if name != seat), "another seat")


def table(records, now):
    """One row per seat: what it is good at, last success, 7-day spend, rest, and who replaces it."""
    now = _aware(now)
    resting = pressure(records, now)
    plan = budget(records, now)
    last_good = _last_good_days(records, now)
    rows = []
    for seat in ("claude", "codex", "gemini", "grok", "qwen", "ollama"):
        info = plan["seats"].get(seat)
        chain = CHAINS[seat]
        replacement = next((name for name in chain[1:] if name not in resting), "")
        rows.append({
            "seat": seat, "good_at": GOOD_AT[seat], "local": seat in LOCAL,
            "used": info["used"] if info else None, "limit": info["limit"] if info else None,
            "calls": info["calls"] if info else None, "last_good_days": last_good.get(seat),
            "resting": resting.get(seat, ""), "replacement": replacement,
        })
    return rows


def render_table(rows):
    lines = [f"{'seat':<8} {'7-day tokens':<16} {'last good':<10} {'state':<10} {'replacement':<12} good at"]
    for row in rows:
        spend = "local, free" if row["limit"] is None else f"{row['used']}/{row['limit']}"
        last = "never" if row["last_good_days"] is None else f"{row['last_good_days']}d"
        state = "resting" if row["resting"] else "open"
        lines.append(f"{row['seat']:<8} {spend:<16} {last:<10} {state:<10} {row['replacement'] or '-':<12} {row['good_at']}")
        if row["resting"]:
            lines.append(f"         {row['resting']}")
    return "\n".join(lines)
