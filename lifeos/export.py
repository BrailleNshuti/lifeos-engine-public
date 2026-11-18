"""`lifeos export --out FILE`: one evidence page for a CV or portfolio: recent proofs, minutes saved, weekly rhythm, the
run-ledger head and your calibration, with every line the guard flags replaced (the page is safe to share).

It reads your logs and writes one new file; it never overwrites and sends nothing anywhere.
"""
import datetime as dt
from pathlib import Path

from . import calibrate, redact, timeline, verify
from .store import read_csv_rows


class ExportError(Exception):
    pass


def build(home, today=None, proofs=20):
    today = today or dt.date.today()
    home = Path(home)
    rows = read_csv_rows(home / "logs" / "proofs.csv")[-proofs:]
    minutes = 0
    for r in read_csv_rows(home / "logs" / "ledger.csv", ("minutes_saved",)):
        try:
            minutes += int(float(r["minutes_saved"]))
        except ValueError:
            continue
    chain = verify.verify_chain(home)
    cal = calibrate.report(home)
    lines = [f"# Evidence · {today.isoformat()}", "",
             "Built by `lifeos export` from my own logs. Every number has a row behind it.", "",
             "## Recent proofs", "", "| date | area | proof | link |", "|---|---|---|---|"]
    lines += [f"| {r.get('date', '')} | {r.get('area', '')} | {r.get('proof', '')} | {r.get('link', '')} |" for r in rows]
    lines += ["", "## Numbers", "", f"- Proofs listed: {len(rows)}", f"- Minutes saved: {minutes}",
              f"- Ledger: {chain['records']} run records, chain {'intact' if chain['ok'] else 'BROKEN'}",
              f"- Ledger head: `{chain['head']}`",
              f"- Predictions: {cal['resolved']} resolved, {cal['open']} open"
              + (f", Brier {cal['brier']:.3f}" if cal["brier"] is not None else ""), "",
              "## Weekly rhythm", "", "```", timeline.render(timeline.weeks(home, today=today, count=8)), "```", ""]
    clean, _ = redact.text("\n".join(lines))
    return clean


def write(home, out, today=None):
    out = Path(out)
    if out.exists():
        raise ExportError(f"{out} exists: exports are never overwritten.")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(home, today=today), encoding="utf-8", newline="\n")
    return out
