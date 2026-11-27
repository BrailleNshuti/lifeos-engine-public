"""Why calls failed, in one word per call, shown by `earn` and `sunday` (round 4 item 9). Made-up records only."""
import datetime as dt
import json

import pytest

from lifeos import earn

TODAY = dt.date(2026, 11, 27)


@pytest.mark.parametrize("rec,kind", [
    ({"status": "timeout", "error": "ollama did not answer within 600 s"}, "timeout"),
    ({"status": "failed", "error": "agy failed: error: Individual quota reached. Resets"}, "quota"),
    ({"status": "failed", "error": "You've hit your usage limit. Upgrade"}, "quota"),
    ({"status": "failed", "error": "grok failed: Error: max turns reached"}, "max_turns"),
    ({"status": "failed", "error": "401 Unauthorized"}, "signin"),
    ({"status": "tool_missing", "error": "codex is not installed"}, "tool_missing"),
    ({"status": "failed", "error": "something odd"}, "other"),
    ({"status": "failed"}, "other"),
])
def test_one_word_per_failure(rec, kind):
    assert earn.failure_kind(rec) == kind


def test_the_report_counts_per_seat_and_leaves_out_blocked_and_old_calls(tmp_path):
    (tmp_path / "logs").mkdir()
    rows = [{"model": "codex", "status": "failed", "error": "usage limit", "date": "2026-11-26"},
            {"model": "codex", "status": "failed", "error": "usage limit", "date": "2026-11-25"},
            {"model": "gemini", "status": "failed", "error": "quota reached", "date": "2026-11-26"},
            {"model": "gemini", "status": "blocked", "date": "2026-11-26"},
            {"model": "gemini", "status": "ok", "date": "2026-11-26"},
            {"model": "qwen:qwen3.5:4b", "status": "timeout", "date": "2026-11-26"},
            {"model": "grok", "status": "failed", "error": "x", "date": "2026-01-01"}]
    (tmp_path / "logs" / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    assert earn.failure_kinds(tmp_path, TODAY) == {"codex": {"quota": 2}, "gemini": {"quota": 1}, "qwen": {"timeout": 1}}


def test_render_adds_a_why_line_only_for_seats_with_failures():
    rows = [{"seat": "codex", "ok": 2, "failed": 2, "median_s": 55.4, "worst_s": 80.4},
            {"seat": "claude", "ok": 3, "failed": 0, "median_s": 18.9, "worst_s": 23.6}]
    text = earn.render_latency(rows, why={"codex": {"quota": 1, "timeout": 1}})
    assert "why: 1 quota, 1 timeout" in text and text.count("why:") == 1
    assert "why" not in earn.render_latency(rows)
