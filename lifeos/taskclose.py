"""`lifeos task close` and `lifeos task block`: finish or pause a task the way the rules ask. Each is one locked, atomic write
and refuses, writing nothing, when it cannot do the whole job.

`close` sets the status to done, writes the proof under `## Proof` and an optional result above it. It refuses without a real
proof (a link, a file, a test or a PR number, the same test `lint` uses), with a TODO finish line, with private data (the
guard), or when the task is already done. `block` sets the status to blocked and adds the reason as a dated update. Only the
front matter (the lines between the first two `---`) is read or changed for `status` and `done_when`; a line like `status:`
in the body is text, not a field. No model is called and nothing is sent."""
import datetime as dt
import re
from pathlib import Path

from . import guard
from .context import task_file
from .lint import has_proof
from .store import atomic_write_bytes, store_lock

FRONT = re.compile(r"\A---\n(.*?\n)---[ \t]*(?:\n|\Z)", re.S)
PROOF_HEADING = re.compile(r"^## Proof[^\n]*(?:\n|\Z)", re.M)


class CloseError(Exception):
    pass


def _find(home, task):
    try:
        return task_file(home, task)
    except (ValueError, FileNotFoundError) as err:
        raise CloseError(str(err)) from None


def _read(path):
    """(text with LF line ends, the newline style of the file, the front matter match, the status word)."""
    raw = path.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n")
    front = FRONT.match(text)
    if not front:
        raise CloseError(f"{path.name} has no closed front matter (the lines between the first two ---).")
    status = re.search(r"^status:[ \t]*([^\n#]*)", front.group(1), re.M)
    if not status:
        raise CloseError(f"{path.name} has no status line in its front matter.")
    return text, nl, front, status.group(1).strip()


def _set_status(text, front, word):
    head = re.sub(r"^status:[^\n]*", f"status: {word}", front.group(1), count=1, flags=re.M)
    return "---\n" + head + text[front.end(1):]


def _place(text, proof, result, today):
    """The text with the proof under its `## Proof` heading (added if there is none) and the result above it, or None when the
    heading cannot be found afterwards."""
    if not PROOF_HEADING.search(text):
        text = text.rstrip("\n") + "\n\n## Proof\n"
    match = PROOF_HEADING.search(text)
    if not match:
        return None
    heading = match.group(0).rstrip("\n")
    block = (f"## Result · you · {today:%Y-%m-%d}\n{result}\n\n" if result else "") + heading + "\n" + proof + "\n"
    return text[:match.start()] + block + text[match.end():]


def close(home, task, proof, result="", today=None):
    """Mark the task done with its proof. Returns the task path. Raises CloseError and writes nothing when it cannot."""
    proof, result = (proof or "").strip(), (result or "").strip()
    today = today or dt.date.today()
    path = _find(home, task)
    for label, text in (("proof", proof), ("result", result)):
        if [f for f in guard.scan_text(text) if f[1] == "BLOCK"]:
            raise CloseError(f"The {label} looks like private data (rule 9). Rewrite it without the number or key.")
    if not has_proof("## Proof\n" + proof):
        raise CloseError("The proof needs something checkable: a link, a file name, a test name or a PR number (rule 1).")
    with store_lock(home):
        text, nl, front, status = _read(path)
        if status == "done":
            raise CloseError(f"{path.stem} is already done.")
        if re.search(r"^done_when:[ \t]*TODO", front.group(1), re.M | re.I):
            raise CloseError("The finish line (done_when) is still TODO. Write it before you close the task.")
        placed = _place(_set_status(text, front, "done"), proof, result, today)
        if placed is None:
            raise CloseError(f"Could not place the proof in {path.name}; nothing was changed.")
        atomic_write_bytes(path, placed.replace("\n", nl).encode("utf-8"))
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
    path = _find(home, task)
    with store_lock(home):
        text, nl, front, status = _read(path)
        if status == "done":
            raise CloseError(f"{path.stem} is already done; a finished task cannot be blocked.")
        text = _set_status(text, front, "blocked").rstrip("\n") + f"\n\n## Update {today:%Y-%m-%d}\nBlocked on purpose: {reason}\n"
        atomic_write_bytes(path, text.replace("\n", nl).encode("utf-8"))
    return Path(path)
