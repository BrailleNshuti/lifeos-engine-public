"""Token savings, measured from your own ledger.

Baseline: what one call would cost if you pasted every note in the home (all .md files outside logs/) into the chat.
Sent: the tokens the engine actually put in the pack for each remote `ask` run (task + rules, trimmed to a budget).
Saved = baseline x runs - sent. The baseline uses the home as it is today, so it is an estimate, and it says so.
"""
from pathlib import Path

from .home import estimate_tokens
from .store import read_run_records

SKIP = {"logs", ".git", ".github", "node_modules"}


def _baseline(home):
    total = 0
    for p in Path(home).rglob("*.md"):
        if SKIP & set(p.relative_to(home).parts[:-1]):
            continue
        try:
            total += estimate_tokens(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    return total


def compute(home):
    runs = [r for r in read_run_records(home)
            if r.get("command") == "ask" and r.get("locality") == "remote" and isinstance(r.get("tokens"), int)]
    sent = sum(r["tokens"] for r in runs)
    base = _baseline(home)
    would = base * len(runs)
    saved = max(would - sent, 0) if runs else 0
    return {"runs": len(runs), "sent": sent, "baseline_each": base, "saved": saved,
            "percent": round(100 * saved / would) if would else 0}


def render(s):
    if not s["runs"]:
        return "No ask runs to a cloud model yet. Run `lifeos ask` and this shows what the context pack saved."
    return (f"{s['runs']} cloud runs sent {s['sent']:,} tokens. Pasting every note each time would have sent about "
            f"{s['baseline_each'] * s['runs']:,}.\nSaved about {s['saved']:,} tokens ({s['percent']} %) "
            f"(estimate: the baseline uses your notes as they are today).")
