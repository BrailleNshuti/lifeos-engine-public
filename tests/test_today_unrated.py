"""`lifeos today` lists answers with no rating yet, and shows days left on waiting items (round 4 items 12 and 26)."""
import datetime as dt
import json
import shutil

import pytest

from lifeos import learn, today

TODAY = dt.date(2026, 11, 27)


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def runs(home, rows):
    (home / "logs").mkdir(exist_ok=True)
    with (home / "logs" / "runs.jsonl").open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps({"command": "ask", "status": "ok", **r}) + "\n")


def test_an_old_answer_without_a_rating_is_listed_once(home):
    runs(home, [{"task_id": "T-261120-a", "model": "gemini", "date": "2026-11-25"},
                {"task_id": "T-261120-a", "model": "gemini", "date": "2026-11-26"}])
    assert today.unrated(home, TODAY) == [{"task": "T-261120-a", "seat": "gemini", "date": "2026-11-25"}]


def test_todays_answer_is_not_nagged_yet(home):
    runs(home, [{"task_id": "T-261127-b", "model": "grok", "date": "2026-11-27"}])
    assert today.unrated(home, TODAY) == []


def test_a_rating_by_prefix_clears_it(home):
    runs(home, [{"task_id": "T-261120-a", "model": "gemini", "date": "2026-11-25"}])
    learn.add_rating(home, "T-261120", "gemini", 4, "summarise a changelog")
    assert today.unrated(home, TODAY) == []


def test_failures_review_runs_and_local_labels(home):
    runs(home, [{"task_id": "T-1", "model": "claude", "date": "2026-11-20", "status": "failed"},
                {"task_id": "T-2", "model": "review", "date": "2026-11-20"},
                {"task_id": "T-3", "model": "ollama:llama3.2", "date": "2026-11-20"}])
    assert [(r["task"], r["seat"]) for r in today.unrated(home, TODAY)] == [("T-3", "ollama")]


def test_garbled_dates_and_a_missing_ledger_do_not_crash(home):
    runs(home, [{"task_id": "T-4", "model": "claude", "date": "soon"}])
    assert today.unrated(home, TODAY) == []
    (home / "logs" / "runs.jsonl").unlink()
    assert today.unrated(home, TODAY) == []


def test_render_shows_the_rate_command_and_days_left(home):
    runs(home, [{"task_id": "T-261120-a", "model": "gemini", "date": "2026-11-25"}])
    (home / "waiting.json").write_text(json.dumps([{"item": "pick one", "who": "you", "when": "2026-11-29"},
                                                   {"item": "old", "who": "you", "when": "2026-11-25"},
                                                   {"item": "later", "who": "you", "when": "anytime"}]), encoding="utf-8")
    out = today.render(today.build(home, TODAY))
    assert "Not rated yet (1)" in out and "lifeos rate T-261120-a gemini" in out
    assert "in 2 days" in out and "2 days late" in out
    assert "anytime)" in out


def test_days_left_wording():
    assert [today.days_left(d, TODAY) for d in ("2026-11-27", "2026-11-28", "2026-12-01", "2026-11-26", "anytime", "")] == \
        ["today", "tomorrow", "in 4 days", "1 days late", "", ""]


def test_coverage_counts_answers_and_ratings_per_seat(home):
    runs(home, [{"task_id": "T-261120-a", "model": "gemini", "date": "2026-11-25"},
                {"task_id": "T-261121-b", "model": "gemini", "date": "2026-11-25"},
                {"task_id": "T-261121-b", "model": "gemini", "date": "2026-11-26"},
                {"task_id": "T-261122-c", "model": "grok", "date": "2026-11-25"},
                {"task_id": "T-9", "model": "review", "date": "2026-11-25"},
                {"task_id": "T-261122-c", "model": "claude", "date": "2026-11-25", "status": "failed"}])
    learn.add_rating(home, "T-261120", "gemini", 4, "summarise a changelog")
    assert today.coverage(home) == {"gemini": {"answered": 2, "rated": 1}, "grok": {"answered": 1, "rated": 0}}
    text = today.render_coverage(today.coverage(home))
    assert "gemini     1 of   2 answers rated" in text and "grok       0 of   1 answers rated   <- not judged yet" in text


def test_coverage_with_no_ledger_says_so(home):
    assert today.coverage(home) == {} and today.render_coverage({}) == "No answers recorded yet."
