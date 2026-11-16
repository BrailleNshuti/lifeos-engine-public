"""Seat choice, cloud budget and usage-limit rest. No model is called."""
import datetime as dt

from lifeos import ask, seats


NOW = dt.datetime(2026, 11, 16, 12, 0, tzinfo=dt.timezone.utc)


def _run(model, status, **extra):
    row = {
        "command": "ask", "model": model, "status": status, "date": "2026-11-16",
        "tokens": 100, "finished_at": "2026-11-16T10:00:00Z",
    }
    row.update(extra)
    return row


def test_locality_matches_the_policy_sets():
    from lifeos import policy
    assert seats.LOCAL == policy.LOCAL_PROVIDERS
    assert seats.REMOTE == policy.REMOTE_PROVIDERS


def test_small_local_jobs_go_to_qwen_and_code_stays_with_claude():
    assert seats.pick("Extract the names into a checklist")[0] == "qwen"
    assert seats.pick("Implement the export function")[0] == "claude"
    assert seats.pick("Run pytest and review the diff")[0] == "codex"


def test_usage_limit_rests_the_seat_until_the_provider_time():
    resting = seats.pressure([
        _run("codex", "failed", error="usage limit. try again at Nov 18th, 2026 4:02 PM"),
    ], NOW)
    assert resting["codex"] == "usage limit until 2026-11-18 16:02 UTC"
    model, reason, chain = seats.choose("Run the pytest", "PERSONAL", resting)
    assert model == "claude" and "codex" not in chain and "skipped codex" in reason


def test_a_later_success_clears_the_rest():
    records = [
        _run("codex", "failed", error="usage limit. try again at Nov 18th, 2026 4:02 PM"),
        _run("codex", "ok", finished_at="2026-11-16T11:00:00Z", error=""),
    ]
    assert "codex" not in seats.pressure(records, NOW)


def test_no_clock_in_the_message_rests_for_twelve_hours():
    resting = seats.pressure([_run("gemini", "failed", error="HTTP 429 quota")], NOW)
    assert resting["gemini"] == "usage limit until 2026-11-16 22:00 UTC"


def test_a_past_reset_does_not_rest_the_seat():
    resting = seats.pressure([
        _run("gemini", "failed", error="usage limit. try again at Nov 15th, 2026 1:00 PM"),
    ], NOW)
    assert "gemini" not in resting


def test_token_share_moves_the_job_to_the_next_open_seat():
    resting = seats.pressure([_run("claude", "ok", tokens=40_000)], NOW)
    assert "40000" in resting["claude"]
    model, _reason, chain = seats.choose("Draft the plan and decide", "PERSONAL", resting)
    assert model == "codex" and chain[0] == "codex" and "claude" not in chain


def test_old_spend_is_outside_the_seven_day_window():
    resting = seats.pressure([
        _run("claude", "ok", tokens=40_000, date="2026-11-01", finished_at="2026-11-01T10:00:00Z"),
    ], NOW)
    assert "claude" not in resting


def test_sensitive_work_never_gains_a_cloud_seat():
    _model, reason, chain = seats.choose("Draft a memo", "SENSITIVE", {}, explicit="claude")
    assert chain == ["qwen", "ollama"]
    assert "laptop" in reason


def test_a_long_banner_keeps_the_usage_limit_sentence():
    banner = ("OpenAI Codex v0.1 " + ("x" * 300)
              + " You've hit your usage limit. try again at Nov 18th, 2026 4:02 PM.")
    text = ask.redact_error(banner)
    assert "usage limit" in text and len(text) <= 240
