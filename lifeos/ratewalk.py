"""`lifeos rate --walk`: rate the answers that `lifeos today` lists as unrated, one after another, at the prompt. No model is
called and nothing is sent. For each answer it shows the task, the seat and the start of that seat's answer, then asks for a
score from 1 to 5 (s skips, q stops) and a note; a score of 1 or 2 needs a note, because that is what teaches the router."""
import re
from pathlib import Path

from . import learn, today
from .context import task_file
from .delegate import task_text
from .store import read_text_retry

SHOW = 300


def _answer_of(path, seat):
    """The start of the last result written by this seat (any `## Result · <seat>...` block), or ''."""
    try:
        raw = read_text_retry(path, errors="replace")
    except OSError:
        return ""
    blocks = [body for who, body in re.findall(r"^## Result · (\S+) · \d{4}-\d{2}-\d{2}\n(.*?)(?=^## |\Z)", raw, re.M | re.S)
              if who.split(":", 1)[0] == seat]
    return " ".join(blocks[-1].split())[:SHOW] if blocks else ""


def walk(home, ask=input, say=print, day=None):
    """Prompt for every unrated answer. Returns the number of ratings saved."""
    items = today.unrated(home, day)
    if not items:
        say("Every answer is rated.")
        return 0
    saved = 0
    for n, item in enumerate(items, 1):
        try:
            path = task_file(home, item["task"])
        except (ValueError, FileNotFoundError):
            continue
        say(f"[{n}/{len(items)}] {item['task']}  seat: {item['seat']}  answered {item['date']}")
        goal = learn.explicit_kind(read_text_retry(path, errors="replace"))
        shown = _answer_of(path, item["seat"])
        say("  answer starts: " + (shown or "(no answer text found)") + ("..." if len(shown) >= SHOW else ""))
        while True:
            raw = ask("  score 1-5 (s skip, q stop): ").strip().lower()
            if raw in ("s", "q", "") or raw in {"1", "2", "3", "4", "5"}:
                break
            say("  type a number from 1 to 5, s or q")
        if raw == "q":
            break
        if raw in ("s", ""):
            continue
        note = ask("  note" + (" (needed for 1 or 2)" if int(raw) <= 2 else "") + ": ").strip()
        if int(raw) <= 2 and not note:
            say("  skipped: a 1 or a 2 needs a note.")
            continue
        try:
            learn.add_rating(home, item["task"], item["seat"], int(raw), task_text(path), note=note,
                             kind=goal if goal else None)
        except learn.LearnError as err:
            say(f"  not saved: {err}")
            continue
        saved += 1
        say(f"  rated {item['seat']} {raw}/5")
    say(f"{saved} rating(s) saved.")
    return saved
