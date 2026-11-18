"""Tamper-evident run ledger: every new record in logs/runs.jsonl carries the SHA-256 of the line before it.

Changing, deleting or reordering any record breaks the chain after it. The last record and a cut-off tail are covered by
an anchor: save `lifeos verify` head hash somewhere outside the file (a commit message, a proof row) and later check it
with `--anchor`. Records written before the chain existed are counted as legacy, not as errors.
"""
import hashlib
import json
from pathlib import Path

ZERO = "0" * 64


def line_hash(line):
    """SHA-256 of one JSONL line's exact bytes, ignoring the line ending (so LF and CRLF checkouts agree)."""
    if isinstance(line, str):
        line = line.encode("utf-8")
    return hashlib.sha256(line.rstrip(b"\r\n")).hexdigest()


def verify_chain(home, anchor=None):
    """Return {ok, records, chained, legacy, head, errors, anchor_found}. Never raises on a damaged log."""
    path = Path(home) / "logs" / "runs.jsonl"
    result = {"ok": True, "records": 0, "chained": 0, "legacy": 0, "head": ZERO, "errors": [], "anchor_found": None}
    if not path.exists():
        if anchor:
            result["anchor_found"] = anchor == ZERO
        return result
    lines = [ln.rstrip(b"\r") for ln in path.read_bytes().split(b"\n") if ln.strip()]
    chain_started, prev, hashes = False, ZERO, {ZERO}
    for number, line in enumerate(lines, 1):
        try:
            rec = json.loads(line.decode("utf-8"))
            if not isinstance(rec, dict):
                raise ValueError("not an object")
        except (UnicodeDecodeError, ValueError):
            result["errors"].append(f"line {number}: not valid JSON")
            chain_started = True
            prev = line_hash(line)
            hashes.add(prev)
            continue
        if "prev_hash" not in rec:
            if chain_started:
                result["errors"].append(f"line {number}: record is not chained (added by hand?)")
            else:
                result["legacy"] += 1
        else:
            chain_started = True
            result["chained"] += 1
            if rec["prev_hash"] != prev:
                result["errors"].append(f"line {number}: chain broken (an earlier record was changed, removed or reordered)")
        prev = line_hash(line)
        hashes.add(prev)
    result["records"] = len(lines)
    result["head"] = prev
    result["ok"] = not result["errors"]
    if anchor:
        result["anchor_found"] = anchor in hashes
    return result


def render(result):
    if result["ok"]:
        text = (f"Ledger chain ok: {result['records']} records ({result['chained']} chained, {result['legacy']} older, unchained)\n"
                f"head {result['head']}")
    else:
        text = "Ledger chain BROKEN:\n" + "\n".join(f"  {e}" for e in result["errors"][:20])
    if result["anchor_found"] is not None:
        text += "\nanchor " + ("found: history up to it is unchanged" if result["anchor_found"] else "NOT found: the log was cut or rewritten")
    return text
