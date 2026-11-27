"""`lifeos waiting`: the hand-kept waiting list (`waiting.json` in the home folder) without editing JSON by hand.

Each entry is {item, who, when}. Adding and removing happen under the store lock with an atomic write, the text is checked
by the guard, and a damaged file is never overwritten: the command stops and says what is wrong. No model is called."""
import json
from pathlib import Path

from . import guard
from .store import atomic_write_bytes, store_lock

FILE = "waiting.json"
ITEM_MAX = 400


class WaitingError(Exception):
    pass


def _path(home):
    return Path(home) / FILE


def read(home):
    """The entries, [] when the file does not exist. Raises WaitingError when it is damaged (so nothing overwrites it)."""
    path = _path(home)
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as err:
        raise WaitingError(f"{FILE} is not valid JSON ({err}). Fix it by hand; nothing was changed.") from None
    if not isinstance(rows, list):
        raise WaitingError(f"{FILE} should hold a list. Nothing was changed.")
    return [r for r in rows if isinstance(r, dict) and str(r.get("item") or "").strip()]


def _write(home, rows):
    atomic_write_bytes(_path(home), (json.dumps(rows, ensure_ascii=False, indent=1) + chr(10)).encode("utf-8"))


def add(home, item, who="you", when="anytime"):
    item, who, when = " ".join(str(item or "").split()), " ".join(str(who or "").split()), " ".join(str(when or "").split())
    if not item:
        raise WaitingError("Say what is waiting, in one sentence.")
    if len(item) > ITEM_MAX:
        raise WaitingError(f"Keep it under {ITEM_MAX} characters; put the detail in a task file.")
    for text in (item, who, when):
        if [f for f in guard.scan_text(text) if f[1] == "BLOCK"]:
            raise WaitingError("The text looks like private data (rule 9). Rewrite it without the number or key.")
    with store_lock(home):
        rows = read(home)
        entry = {"item": item, "who": who or "you", "when": when or "anytime"}
        _write(home, rows + [entry])
    return entry


def remove(home, number):
    """Remove entry `number` (1 is the first, as `waiting list` shows). Returns the removed entry."""
    with store_lock(home):
        rows = read(home)
        if not 1 <= number <= len(rows):
            raise WaitingError(f"There is no entry {number}; the list has {len(rows)}.")
        gone = rows.pop(number - 1)
        _write(home, rows)
    return gone


def render(rows):
    if not rows:
        return "Nothing is waiting."
    return chr(10).join(f"{n:>2}. {r['item']}  ({r.get('who', '?')}, {r.get('when', '?')})" for n, r in enumerate(rows, 1))
