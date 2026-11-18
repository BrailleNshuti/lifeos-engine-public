"""Quiz built from your own mistakes: the verified questions you missed most and have not yet fixed.

Reads logs/study-attempts.jsonl. A question counts when it is verified or trusted and its latest ratings are bad.
Score = 2 x 'again' + 1 x 'hard' over the last six attempts, minus 2 per 'good'/'easy' since the last miss,
so a question you answered well twice in a row drops out. Prompts only: answers stay hidden until you ask for them.
"""
from . import study

WINDOW = 6


def quiz(home, count=5):
    by_q = {}
    for row in study.attempts(home):
        by_q.setdefault(row["question_id"], []).append(row.get("rating"))
    prompts = {}
    for bank in study.list_banks(home, include_questions=True):
        for q in bank["questions"]:
            if q.get("trust") in ("verified", "trusted"):
                prompts[q["id"]] = {"id": q["id"], "prompt": q.get("prompt", ""), "bank": bank["path"],
                                    "citation": q.get("citation", "")}
    scored = []
    for qid, ratings in by_q.items():
        if qid not in prompts:
            continue
        recent = ratings[-WINDOW:]
        score = 2 * recent.count("again") + recent.count("hard")
        since = 0
        for r in reversed(ratings):
            if r in ("again", "hard"):
                break
            since += 1
        score -= 2 * since
        if score > 0:
            scored.append((score, qid))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [{**prompts[qid], "weight": score} for score, qid in scored[:max(1, int(count))]]
