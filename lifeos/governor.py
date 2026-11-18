"""Budget governor: hold an `ask` before it is sent when the week's cloud budget or the seat cannot take it.

It reads the same numbers as `lifeos seats` (weekly cloud token and call caps, each seat's share, seats resting after a
usage limit) and adds the cost of the call about to be made. Local seats never use the cloud budget. The budget is in
tokens and calls because the engine talks to subscription command-line tools; it has no euro prices. `--force` overrides.
"""
import datetime as dt

from . import seats
from .store import read_run_records


def check(home, model, tokens, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    records = read_run_records(home)
    plan = seats.budget(records, now)
    week = {k: plan[k] for k in ("used_tokens", "cap_tokens", "used_calls", "cap_calls")}
    seat = seats.seat_name(model)
    out = {"seat": seat or model, "estimate": tokens, "allowed": True, "reasons": [], "note": "", "week": week}
    if not seat or seat in seats.LOCAL:
        out["note"] = "local seat: stays on this laptop, no cloud budget used"
        return out
    resting = seats.pressure(records, now).get(seat)
    if resting:
        out["reasons"].append(f"{seat} is resting: {resting}")
    info = plan["seats"].get(seat, {})
    if week["used_tokens"] + tokens > week["cap_tokens"]:
        out["reasons"].append(f"this call (~{tokens} tokens) would take the week past the cloud cap "
                              f"({week['used_tokens']} of {week['cap_tokens']} used)")
    elif info and info["used"] + tokens > info["limit"] and info["used"] > 0:
        out["reasons"].append(f"this call (~{tokens} tokens) would take {seat} past its limit "
                              f"({info['used']} of {info['limit']} used)")
    if week["used_calls"] + 1 > week["cap_calls"]:
        out["reasons"].append(f"the weekly call cap is reached ({week['used_calls']} of {week['cap_calls']})")
    out["allowed"] = not out["reasons"]
    out["note"] = (f"week: {week['used_tokens']} of {week['cap_tokens']} tokens, {week['used_calls']} of {week['cap_calls']} calls; "
                   f"this call ~{tokens} tokens")
    return out


def render(out):
    if out["allowed"]:
        return f"budget governor: ok. {out['note']}"
    return "budget governor: HELD. " + " ".join(out["reasons"])
