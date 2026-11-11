"""lifeos sort-csv: add a spending category to each row of a bank CSV, fully on this computer.

Private by design: only a local Ollama model is allowed, the file is never printed or logged, the result is never
written inside a git repo, and nothing existing is overwritten. Free keyword rules go first; the model only sees
the text of rows the rules cannot place. Model answers outside the category list become 'other' and are flagged.
"""
import csv
import io
import os
import re
import urllib.parse
from pathlib import Path

from . import ask

CATEGORIES = ["groceries", "rent", "transport", "subscriptions", "dining", "utilities", "shopping", "income", "cash", "other"]
RULES = [
    ("income", r"gehalt|salary|lohn|payroll"),
    ("rent", r"miete|\brent\b"),
    ("groceries", r"rewe|aldi|lidl|edeka|penny|kaufland|rossmann|dm[- ]drogerie"),
    ("subscriptions", r"netflix|spotify|prime video|icloud|youtube|abo\b|subscription"),
    ("transport", r"deutsche bahn|\bdb\b|flixbus|uber|bolt|tankstelle|aral|shell|swb|vrs|bonn.?ticket"),
    ("dining", r"restaurant|caf[eé]|pizza|burger|mcdonald|starbucks|lieferando|imbiss"),
    ("utilities", r"strom|stadtwerke|telekom|vodafone|internet|wasser|energie"),
    ("cash", r"geldautomat|bargeld|\batm\b"),
]
DESC_HINTS = r"beschreibung|verwendungszweck|buchungstext|description|memo|merchant|payee|empf|name|text"
COLUMNS = ("lifeos_category", "lifeos_check")


class Refused(Exception):
    """A privacy rule stopped the job; nothing was written."""


def require_local():
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    name = urllib.parse.urlparse(host if "://" in host else "http://" + host).hostname
    if name not in ("localhost", "127.0.0.1", "::1"):
        raise Refused(f"OLLAMA_HOST points to '{name}'. Bank data only goes to a local model on this computer.")


def ask_local(prompt):
    return ask._ollama(prompt, ask._qwen_model(), {"temperature": 0, "num_predict": 12})


def _in_git_repo(path):
    return any((p / ".git").exists() for p in [path.resolve().parent, *path.resolve().parent.parents])


def _by_rule(text, categories):
    for category, words in RULES:
        if category in categories and re.search(words, text, re.I):
            return category
    return None


def _by_model(text, categories, ask_fn):
    prompt = (f"Pick the one category for this bank transaction. Categories: {', '.join(categories)}. "
              f"Answer with the category word only.\nTransaction text: <<<{text[:200]}>>>")
    answer = re.sub(r"[^a-z ]", "", ask_fn(prompt).lower()).strip()
    if answer in categories:
        return answer, ""
    found = [c for c in categories if re.search(rf"\b{re.escape(c)}\b", answer)]
    return (found[0] if found else _other(categories)), "yes"


def _other(categories):
    return "other" if "other" in categories else categories[-1]


def _column(header, name):
    names = [h.strip().lower() for h in header]
    if name:
        if name.lower() not in names:
            raise Refused(f"No column '{name}'. Columns: {', '.join(header)}.")
        return names.index(name.lower())
    for i, h in enumerate(names):
        if re.search(DESC_HINTS, h):
            return i
    raise Refused(f"Could not find the text column. Use --column. Columns: {', '.join(header)}.")


def _read(src):
    text = Path(src).read_text(encoding="utf-8-sig")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return list(csv.reader(io.StringIO(text, newline=""), dialect)), dialect.delimiter


def _check_paths(out):
    if out.exists():
        raise Refused(f"{out.name} already exists; nothing was overwritten. Choose another --out.")
    if _in_git_repo(out):
        raise Refused("The output would be inside a git repo. Bank data never goes into a repo; choose --out elsewhere.")


def sort_csv(src, out=None, column=None, categories=None, ask_fn=None):
    """Write a copy of the CSV with lifeos_category and lifeos_check columns. Returns counts only."""
    src = Path(src)
    out = Path(out) if out else src.with_name(src.stem + ".sorted.csv")
    categories = categories or CATEGORIES
    _check_paths(out)
    rows, delimiter = _read(src)
    if not rows:
        raise Refused("The file is empty.")
    header, data = rows[0], rows[1:]
    col, cache = _column(header, column), {}
    counts = {"rows": len(data), "by_rule": 0, "by_model": 0, "flagged": 0}
    result = [header + list(COLUMNS)]
    for row in data:
        text = row[col].strip() if col < len(row) else ""
        category, check = _by_rule(text, categories), ""
        if category:
            counts["by_rule"] += 1
        else:
            if text not in cache:
                cache[text] = _by_model(text, categories, ask_fn or ask_local) if text else (_other(categories), "yes")
            category, check = cache[text]
            counts["by_model"] += 1
        counts["flagged"] += bool(check)
        result.append(row + [category, check])
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f, delimiter=delimiter).writerows(result)
    return {**counts, "out": out}
