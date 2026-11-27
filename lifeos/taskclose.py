"""`lifeos task close`: finish a task the way the rules ask. Status becomes done, the proof is written under `## Proof`, and
an optional result is added, all in one locked, atomic write. It refuses when there is no real proof (a link, a file, a test
or a PR number, the same test `lint` uses), when the finish line is still TODO, or when the text holds anything the guard would
block. Nothing is sent anywhere; no model is called."""
import datetime as dt
import re
from pathlib import Path

from . import guard
from .context import task_file
from .lint import has_proof
from .store import atomic_write_bytes, store_lock


class CloseError(Exception):
    pass


def close(home, task, proof, result="", today=None):
    """Mark the task done with its proof. Returns the task path. Raises CloseError and writes nothing when it cannot."""
    proof, result = (proof or "").strip(), (result or "").strip()
    today = today or dt.date.today()
    try:
        path = task_file(home, task)
    except (ValueError, FileNotFoundError) as err:
        raise CloseError(str(err)) from None
    for label, text in (("proof", proof), ("result", result)):
        if [f for f in guard.scan_text(text) if f[1] == "BLOCK"]:
            raise CloseError(f"The {label} looks like private data (rule 9). Rewrite it without the number or key.")
    if not has_proof("## Proof\n" + proof):
        raise CloseError("The proof needs something checkable: a link, a file name, a test name or a PR number (rule 1).")
    with store_lock(home):
        raw = path.read_bytes().decode("utf-8")
        nl = "\r\n" if "\r\n" in raw else "\n"
        text = raw.replace("\r\n", "\n")
        status = re.search(r"^status:[ \t]*(\S*)", text, re.M)
        if not status or not text.startswith("---\n"):
            raise CloseError(f"{path.name} has no front matter with a status line.")
        if status.group(1) == "done":
            raise CloseError(f"{path.stem} is already done.")
        if re.search(r"^done_when:[ \t]*TODO", text, re.M | re.I):
            raise CloseError("The finish line (done_when) is still TODO. Write it before you close the task.")
        if "\n## Proof" not in text:
            text = text.rstrip("\n") + "\n\n## Proof\n"
        text = re.sub(r"^status:[ \t]*\S*", "status: done", text, count=1, flags=re.M)
        text = re.sub(r"(^## Proof[ \t]*\n)", lambda m: m.group(1) + proof + "\n", text, count=1, flags=re.M)
        if result:
            text = re.sub(r"(^## Proof[ \t]*\n)", lambda m: f"## Result · you · {today:%Y-%m-%d}\n{result}\n\n" + m.group(1), text, count=1, flags=re.M)
        atomic_write_bytes(path, text.replace("\n", nl).encode("utf-8"))
    return Path(path)


def block(home, task, reason, today=None):
    """Pause a task on purpose: status becomes blocked and the reason is written as a dated update. Returns the task path.
    Raises CloseError and writes nothing for a done task, an empty reason, private text or an unknown id."""
    reason = " ".join((reason or "").split())
    today = today or dt.date.today()
    if not reason:
        raise CloseError("Say why it is blocked, in one sentence.")
    if [f for f in guard.scan_text(reason) if f[1] == "BLOCK"]:
        raise CloseError("The reason looks like private data (rule 9). Rewrite it without the number or key.")
    try:
        path = task_file(home, task)
    except (ValueError, FileNotFoundError) as err:
        raise CloseError(str(err)) from None
    with store_lock(home):
        raw = path.read_bytes().decode("utf-8")
        nl = "\r\n" if "\r\n" in raw else "\n"
        text = raw.replace("\r\n", "\n")
        status = re.search(r"^status:[ \t]*(\S*)", text, re.M)
        if not status or not text.startswith("---\n"):
            raise CloseError(f"{path.name} has no front matter with a status line.")
        if status.group(1) == "done":
            raise CloseError(f"{path.stem} is already done; a finished task cannot be blocked.")
        text = re.sub(r"^status:[ \t]*\S*", "status: blocked", text, count=1, flags=re.M)
        text = text.rstrip("\n") + f"\n\n## Update {today:%Y-%m-%d}\nBlocked on purpose: {reason}\n"
        atomic_write_bytes(path, text.replace("\n", nl).encode("utf-8"))
    return Path(path)
