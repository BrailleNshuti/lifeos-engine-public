"""Your own German vocabulary: words from your own life, reviewed on a simple box schedule.

`add` stores a word, its meaning and an example sentence from your own day (logs/vocab.csv, append-only).
`answer` records a hit or a miss. Box = hits in a row (a miss resets to 0); the next review comes after
1, 3, 7, 14 days for boxes 1 to 4. New words are due at once. No model is called and nothing is sent anywhere.
"""
import csv
import datetime as dt
from pathlib import Path

from . import guard
from .store import append_csv_row_creating, read_csv_rows

HEADER = ["date", "word", "kind", "value", "text"]
GAPS = [0, 1, 3, 7, 14]


class VocabError(Exception):
    pass


def _path(home):
    return Path(home) / "logs" / "vocab.csv"


def _rows(home):
    return read_csv_rows(_path(home), ("word", "kind"))


def _append(home, values):
    path = _path(home)
    append_csv_row_creating(path, HEADER, values)


def _clean(value, limit):
    return " ".join(str(value or "").split())[:limit]


def add(home, word, meaning, example="", today=None):
    word, meaning, example = _clean(word, 80), _clean(meaning, 120), _clean(example, 200)
    if not word or not meaning:
        raise VocabError("A word and its meaning are both needed.")
    if guard.scan_text(f"{word}\n{meaning}\n{example}"):
        raise VocabError("This looks like private data (rule 9). Keep it out of the vocabulary list.")
    if any(r["word"].lower() == word.lower() and r["kind"] == "add" for r in _rows(home)):
        raise VocabError(f"'{word}' is already in the list.")
    day = (today or dt.date.today()).isoformat()
    _append(home, [day, word, "add", meaning, example])


def answer(home, word, hit, today=None):
    key = _clean(word, 80).lower()
    match = next((r["word"] for r in _rows(home) if r["kind"] == "add" and r["word"].lower() == key), None)
    if match is None:
        raise VocabError(f"'{word}' is not in the list. Add it first.")
    _append(home, [(today or dt.date.today()).isoformat(), match, "review", 1 if hit else 0, ""])


def stats(home, today=None):
    today = today or dt.date.today()
    words = {}
    for r in _rows(home):
        w = words.setdefault(r["word"], {"word": r["word"], "meaning": "", "example": "", "box": 0, "last": None})
        if r["kind"] == "add":
            w["meaning"], w["example"] = r["value"], r["text"]
        else:
            w["box"] = min(w["box"] + 1, len(GAPS) - 1) if r["value"] == "1" else 0
            w["last"] = dt.date.fromisoformat(r["date"])
    for w in words.values():
        w["due"] = w["last"] is None or today >= w["last"] + dt.timedelta(days=GAPS[w["box"]] if w["box"] else 0)
        if w["last"] is not None and w["box"] == 0:
            w["due"] = True
    return {"words": list(words.values()), "due": sum(1 for w in words.values() if w["due"])}


def due(home, today=None):
    return [w for w in stats(home, today)["words"] if w["due"]]
