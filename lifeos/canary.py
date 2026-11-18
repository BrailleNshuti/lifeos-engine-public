"""Canaries and the guard score.

`guard_score` generates checksum-valid but made-up IBANs and card numbers (seeded, so every run is the same) in many
layouts, plus tokens and an ID line, and counts how many the guard blocks. It also checks that ordinary text is not
flagged. `outbound_check` plants one of each kind in a throwaway task and proves ask refuses to send it: no model is
called and no canary reaches logs/runs.jsonl. Nothing real is used and nothing is written outside a temp folder.
"""
import datetime as dt
import random
import string
import tempfile
from pathlib import Path

from . import ask
from .guard import scan_text

SEED = 20261118
IBAN_SPECS = [("DE", 18), ("GB", 18), ("FR", 23), ("ES", 20), ("NL", 14), ("IT", 23), ("BE", 12), ("AT", 16)]
CARD_SPECS = [("4", 16), ("51", 16), ("37", 15), ("6011", 16), ("35", 16), ("4", 13)]
BENIGN = [
    "released 2026-11-18 at 01:13",
    "commit 8feecc5a1b2c3d4e5f60718293a4b5c6d7e8f901",
    "version 0.3.0 and 10.20.30.40",
    "a decimal 4111111111111111.5 stays a number",
    "ratio 1234.5678.9012 is not a card",
    "the rule 12 says no personal data",
    "be12 is a short word pair",
]


def _grouped(value, size=4, sep=" "):
    return sep.join(value[i:i + size] for i in range(0, len(value), size))


def _iban(rnd, country, length):
    bban = "".join(rnd.choice(string.digits) for _ in range(length))
    digits = "".join(str(int(c, 36)) for c in bban + country + "00")
    return f"{country}{98 - int(digits) % 97:02d}{bban}"


def _card(rnd, prefix, total):
    body = prefix + "".join(rnd.choice(string.digits) for _ in range(total - len(prefix) - 1))
    s = 0
    for i, c in enumerate(reversed(body)):
        d = int(c)
        if i % 2 == 0:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        s += d
    return body + str((10 - s % 10) % 10)


IBAN_LAYOUTS = {
    "plain": lambda v: v, "grouped": _grouped, "lowercase": lambda v: v.lower(),
    "lowercase grouped": lambda v: _grouped(v).lower(), "dashes": lambda v: _grouped(v, sep="-"),
    "dots": lambda v: _grouped(v, sep="."), "sentence": lambda v: f"Please pay to {_grouped(v)}.",
    "after colon": lambda v: f"IBAN:{v}",
}
CARD_LAYOUTS = {
    "plain": lambda v: v, "spaced": _grouped, "dashes": lambda v: _grouped(v, sep="-"),
    "dots": lambda v: _grouped(v, sep="."), "end of sentence": lambda v: f"My card is {_grouped(v)}.",
    "end of sentence plain": lambda v: f"n={v}.", "brackets": lambda v: f"({_grouped(v)})",
}


def canaries(seed=SEED, per_spec=4):
    """Return [(kind, layout, text)]: made-up identifiers in many layouts. Deterministic for a seed."""
    rnd = random.Random(seed)
    out = []
    for country, length in IBAN_SPECS:
        for _ in range(per_spec):
            value = _iban(rnd, country, length)
            out += [("IBAN", name, fn(value)) for name, fn in IBAN_LAYOUTS.items()]
    for prefix, total in CARD_SPECS:
        for _ in range(per_spec):
            value = _card(rnd, prefix, total)
            out += [("Card number", name, fn(value)) for name, fn in CARD_LAYOUTS.items()]
    token = "".join(rnd.choice(string.ascii_letters + string.digits) for _ in range(36))
    out += [("GitHub token", "assigned", "token " + "ghp_" + token),
            ("API key", "plain", "key " + "sk-ant-" + token),
            ("Private key", "header", "-----BEGIN " + "RSA PRIVATE KEY-----"),
            ("ID number", "labelled", "Passport: " + "C0" + "".join(rnd.choice(string.digits) for _ in range(7)))]
    return out


def _blocks(text):
    return any(sev == "BLOCK" for _, sev, _, _ in scan_text(text))


def guard_score(seed=SEED):
    items = canaries(seed)
    misses = [f"{kind} / {layout}" for kind, layout, text in items if not _blocks(text)]
    flagged = [text for text in BENIGN if _blocks(text)]
    return {"total": len(items), "blocked": len(items) - len(misses), "misses": misses,
            "benign_total": len(BENIGN), "benign_flagged": flagged}


def outbound_check():
    """Plant one canary of each kind in a throwaway task and prove ask refuses to send it."""
    result = {"ok": False, "model_calls": 0, "kinds_stopped": 0, "kinds_total": 0, "leaked_into_logs": []}
    singles = {}
    for kind, _, text in canaries(per_spec=1):
        singles.setdefault(kind, text)
    calls = []

    def adapter(prompt):
        calls.append(prompt)
        return "should never be reached"

    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        (home / "logs").mkdir()
        (home / "tasks").mkdir()
        (home / "now.md").write_text("# Now\n", encoding="utf-8")
        (home / "rules.md").write_text("# Rules\n", encoding="utf-8")
        for number, (kind, text) in enumerate(sorted(singles.items()), 1):
            task = home / "tasks" / f"T-261118-canary-{number}.md"
            task.write_text(f"---\nid: {task.stem}\ngoal: canary\ndone_when: n/a\nroute: x\nlevel: L2\nstatus: inbox\n---\n"
                            f"## Context\n\n## Task\n{text}\n", encoding="utf-8")
            result["kinds_total"] += 1
            try:
                ask.run_ask(home, "claude", task.stem, adapters={"claude": adapter}, today=dt.date(2026, 11, 18))
            except ask.Blocked:
                result["kinds_stopped"] += 1
        logs = (home / "logs" / "runs.jsonl").read_text(encoding="utf-8") if (home / "logs" / "runs.jsonl").exists() else ""
        result["leaked_into_logs"] = [kind for kind, text in singles.items() if text and text.split()[-1] in logs]
    result["model_calls"] = len(calls)
    result["ok"] = (not calls and result["kinds_stopped"] == result["kinds_total"] and not result["leaked_into_logs"])
    return result


def render(guard, outbound):
    lines = [f"Guard score: {guard['blocked']} of {guard['total']} generated identifiers blocked "
             f"({len(guard['misses'])} missed); {len(guard['benign_flagged'])} of {guard['benign_total']} ordinary texts wrongly flagged.",
             f"Outbound canaries: {outbound['kinds_stopped']} of {outbound['kinds_total']} kinds stopped before sending; "
             f"model calls {outbound['model_calls']}; leaked into logs {len(outbound['leaked_into_logs'])}."]
    lines += [f"  MISSED {m}" for m in guard["misses"][:10]]
    return "\n".join(lines)
