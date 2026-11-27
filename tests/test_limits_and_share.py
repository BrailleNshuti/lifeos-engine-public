"""A calendar of usage-limit days per seat in `earn`, and a weekly-share line after each cloud call (round 5 items 5 and 6)."""
import datetime as dt
import json

from lifeos import earn, egress

TODAY = dt.date(2026, 11, 28)


def write(home, rows):
    (home / "logs").mkdir(exist_ok=True)
    (home / "logs" / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_the_days_a_seat_hit_its_limit_are_listed_once_each(tmp_path):
    write(tmp_path, [{"model": "codex", "status": "failed", "error": "usage limit", "date": "2026-11-26"},
                     {"model": "codex", "status": "failed", "error": "usage limit", "date": "2026-11-26"},
                     {"model": "codex", "status": "failed", "error": "usage limit", "date": "2026-11-27"},
                     {"model": "gemini", "status": "failed", "error": "Individual quota reached", "date": "2026-11-26"},
                     {"model": "grok", "status": "failed", "error": "max turns reached", "date": "2026-11-26"},
                     {"model": "claude", "status": "ok", "date": "2026-11-26"},
                     {"model": "codex", "status": "failed", "error": "usage limit", "date": "2026-01-01"}])
    assert earn.limit_days(tmp_path, TODAY) == {"codex": ["2026-11-26", "2026-11-27"], "gemini": ["2026-11-26"]}


def test_render_adds_the_calendar_line_only_for_seats_that_hit_a_limit():
    rows = [{"seat": "codex", "ok": 2, "failed": 2, "median_s": 55.4, "worst_s": 80.4},
            {"seat": "claude", "ok": 3, "failed": 0, "median_s": 18.9, "worst_s": 23.6}]
    text = earn.render_latency(rows, limits={"codex": ["2026-11-26", "2026-11-27"]})
    assert "usage limit hit on: 2026-11-26, 2026-11-27" in text and text.count("usage limit hit on") == 1
    assert "usage limit" not in earn.render_latency(rows)


def test_the_share_line_counts_the_last_seven_days_only(tmp_path):
    write(tmp_path, [{"model": "claude", "status": "ok", "tokens": 4000, "date": "2026-11-27"},
                     {"model": "claude", "status": "ok", "tokens": 9000, "date": "2026-11-01"}])
    assert egress.share_line(tmp_path, "claude", TODAY) == "weekly share: claude 4,000 of 40,000 tokens in the last 7 days (10 %)"


def test_local_seats_and_unknown_seats_print_nothing(tmp_path):
    write(tmp_path, [{"model": "qwen", "status": "ok", "tokens": 4000, "date": "2026-11-27"}])
    assert egress.share_line(tmp_path, "qwen", TODAY) == "" and egress.share_line(tmp_path, "nobody", TODAY) == ""
    assert egress.share_line(tmp_path, "claude", TODAY).startswith("weekly share: claude 0 of 40,000")
