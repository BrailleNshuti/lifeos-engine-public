"""`lifeos demo`: the engine's main promises, shown on made-up data in a throwaway folder. No account, no model, no network.

Five steps, each checked by code, not narrated: the guard refuses a fake secret, a blind panel surfaces a conflict,
the ledger notices an edit, replay proves an input, and the anchor catches a cut-off tail.
"""
import datetime as dt
import json
import shutil
import tempfile
from pathlib import Path

from . import ask, guard, panel, replay, verify

DAY = dt.date(2026, 11, 20)
TASK = "T-261116"
FAKE_KEY = "sk-ant-api03-" + "a1B2c3D4" * 5


def _home(example):
    root = Path(tempfile.mkdtemp(prefix="lifeos-demo-"))
    shutil.copytree(example, root / "home")
    return root, root / "home"


def run(example=None):
    example = Path(example or Path(__file__).resolve().parent.parent / "examples" / "demo-home")
    root, home = _home(example)
    steps = []

    def step(name, ok, detail):
        steps.append({"step": name, "ok": bool(ok), "detail": detail})

    try:
        hits = guard.scan_text("note: " + FAKE_KEY)
        step("guard blocks a fake secret", any(h[1] == "BLOCK" for h in hits), "a made-up API key was refused, shown masked")
        fakes = {"claude": lambda p: "- Use sqlite\n- The limit is 14 calls",
                 "codex": lambda p: "- Use sqlite\n- The limit is 15 calls"}
        out = panel.run_panel(home, ["claude", "codex"], TASK, adapters=fakes, today=DAY)
        step("blind panel finds a conflict", out["report"]["conflicts"],
             f"two models, same input, {len(out['report']['conflicts'])} conflict(s): 14 calls against 15 calls")
        first = verify.verify_chain(home)
        log = home / "logs" / "runs.jsonl"
        lines = log.read_text(encoding="utf-8").splitlines()
        head = first["head"]
        tampered = json.loads(lines[0])
        tampered["status"] = "failed"
        log.write_text("\n".join([json.dumps(tampered)] + lines[1:]) + "\n", encoding="utf-8")
        broken = verify.verify_chain(home)
        step("ledger stays tamper-evident", first["ok"] and not broken["ok"],
             f"intact with {first['chained']} chained runs; after editing one record: {broken['errors'][0]}")
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        rid = next(iter(out["run_ids"].values()))
        rep = replay.replay_run(home, rid)
        step("replay proves the input", rep.get("identical"), f"{rid}: the same files, the same bytes")
        log.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
        cut = verify.verify_chain(home, anchor=head)
        step("a cut tail is caught by the anchor", cut["anchor_found"] is False,
             "the last record was removed; the saved head hash no longer appears")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return steps


def render(steps):
    lines = ["lifeos demo: made-up data, nothing leaves this computer", ""]
    for i, s in enumerate(steps, 1):
        lines.append(f"{i}. [{'ok' if s['ok'] else 'FAIL'}] {s['step']}\n   {s['detail']}")
    lines.append("")
    lines.append("All five held." if all(s["ok"] for s in steps) else "Something did not hold: run `lifeos prove`.")
    return "\n".join(lines)
