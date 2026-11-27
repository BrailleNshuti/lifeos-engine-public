"""Free notes around one `lifeos ask` call: what the seat cannot do (before), the CHECK line and a number comparison with
an earlier seat's answer (after). No model call."""
import re

from .check import check_answer, task_check_inputs

RESULT = re.compile(r"^## Result · (\S+) · \d{4}-\d{2}-\d{2}\n(.*?)(?=^## |\Z)", re.M | re.S)
NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w])")


def pre_notes(home, model, task):
    """Hints printed before a call (never blocks): what this seat cannot do. Never raises."""
    try:
        from .context import task_file
        from .delegate import task_text
        from .seats import seat_warning
        hint = seat_warning(model, task_text(task_file(home, task)))
        return [hint] if hint else []
    except Exception:
        return []


def numbers_in(text):
    """The numbers of two or more digits (or with a decimal part) in a text, commas removed, as a set of strings."""
    found = set()
    for raw in NUMBER.findall(text or ""):
        n = raw.replace(",", "")
        if "." in n or len(n.replace(".", "")) >= 2:
            found.add(n)
    return found


def disagreements(raw):
    """When the last answer in a task file and the latest earlier answer by another seat share a number but also each hold
    numbers the other lacks, say so: that is where two seats may disagree. Returns a list of 0 or 1 lines."""
    blocks = [(who, body) for who, body in RESULT.findall(raw or "")]
    if len(blocks) < 2:
        return []
    last_who, last_body = blocks[-1]
    for who, body in reversed(blocks[:-1]):
        if who != last_who:
            a, b = numbers_in(last_body), numbers_in(body)
            only_a, only_b = sorted(a - b), sorted(b - a)
            if a & b and only_a and only_b:
                return [f"NUMBERS differ between {last_who} and {who}: only {last_who}: {', '.join(only_a[:4])}; "
                        f"only {who}: {', '.join(only_b[:4])}. Check which is right before you rely on either."]
            return []
    return []


def post_notes(path):
    """The free CHECK line for the answer just written to the task file (same as delegate prints), then a number comparison
    with an earlier seat's answer. Never raises."""
    out = []
    try:
        from .delegate import last_result
        found = check_answer(last_result(path), *task_check_inputs(path))
        if found:
            out.append("CHECK (free, no model): " + "; ".join(found))
    except Exception:
        pass
    try:
        from pathlib import Path
        out += disagreements(Path(path).read_text(encoding="utf-8", errors="replace"))
    except Exception:
        pass
    return out
