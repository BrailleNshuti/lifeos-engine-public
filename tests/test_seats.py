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
    assert resting["codex"] == "usage limit until 2026-11-18 16:02 UTC (no timezone given, read as UTC)"
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
    assert resting["gemini"] == "usage limit until 2026-11-16 22:00 UTC (no time in the message, 12 h rest)"


def test_a_reset_before_the_failure_is_not_trusted():
    """A reset time older than the failure itself is a misread clock: rest 12 h instead."""
    resting = seats.pressure([
        _run("gemini", "failed", error="usage limit. try again at Nov 15th, 2026 1:00 PM"),
    ], NOW)
    assert resting["gemini"] == "usage limit until 2026-11-16 22:00 UTC (reset time was before the failure, 12 h rest)"


def test_a_reset_far_in_the_future_is_capped_at_eight_days():
    resting = seats.pressure([
        _run("codex", "failed", error="usage limit. try again at Dec 30th, 2026 1:00 PM"),
    ], NOW)
    assert resting["codex"] == "usage limit until 2026-11-24 10:00 UTC (reset time was over 8 days away, capped)"


def test_an_explicit_timezone_is_converted_not_assumed():
    resting = seats.pressure([
        _run("codex", "failed", error="usage limit. try again at Nov 18th, 2026 4:02 PM UTC+1"),
    ], NOW)
    assert resting["codex"] == "usage limit until 2026-11-18 15:02 UTC"
    resting = seats.pressure([
        _run("claude", "failed", error="usage limit reached. resets 2026-11-18T16:02:00+02:00"),
    ], NOW)
    assert resting["claude"] == "usage limit until 2026-11-18 14:02 UTC"
    resting = seats.pressure([
        _run("gemini", "failed", error="usage limit. try again at 2026-11-17T08:00:00Z"),
    ], NOW)
    assert resting["gemini"] == "usage limit until 2026-11-17 08:00 UTC"


def test_the_real_codex_message_rests_codex_without_another_call():
    """Recorded wording of the 18 Nov Codex limit: one stored failure is enough."""
    banner = ("OpenAI Codex v0.1 " + ("x" * 300)
              + " You've hit your usage limit. try again at Nov 18th, 2026 4:02 PM.")
    resting = seats.pressure([_run("codex", "failed", error=ask.redact_error(banner))], NOW)
    assert resting["codex"].startswith("usage limit until 2026-11-18 16:02 UTC")


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


def test_one_budget_is_the_lower_of_seat_share_and_weekly_cap(monkeypatch):
    monkeypatch.setattr(seats, "WEEKLY_TOKENS", 50_000)
    records = [_run("codex", "ok", tokens=30_000), _run("gemini", "ok", tokens=10_000), _run("claude", "ok", tokens=15_000)]
    plan = seats.budget(records, NOW)
    assert plan["cap_tokens"] == 50_000 and plan["used_tokens"] == 55_000
    assert plan["seats"]["claude"]["limit"] == 10_000  # 50k cap minus the 40k the other seats spent
    assert plan["seats"]["codex"]["limit"] == 25_000  # 50k cap minus the 25k the others spent, below its 40k share
    monkeypatch.setattr(seats, "WEEKLY_TOKENS", 200_000)
    assert seats.budget(records, NOW)["seats"]["codex"]["limit"] == 40_000  # share is the lower ruler again
    monkeypatch.setattr(seats, "WEEKLY_TOKENS", 50_000)
    resting = seats.pressure(records, NOW)
    assert "weekly cloud cap" in resting["claude"]


def test_local_seats_do_not_spend_the_cloud_budget():
    plan = seats.budget([_run("qwen", "ok", tokens=90_000)], NOW)
    assert plan["used_tokens"] == 0 and plan["used_calls"] == 0


def test_the_weekly_call_cap_rests_every_cloud_seat(monkeypatch):
    monkeypatch.setattr(seats, "WEEKLY_CALLS", 3)
    records = [_run("claude", "ok", tokens=1), _run("codex", "ok", tokens=1), _run("gemini", "ok", tokens=1)]
    resting = seats.pressure(records, NOW)
    assert set(resting) == {"claude", "codex", "gemini", "grok"} and "weekly cloud call cap" in resting["claude"]


def test_a_small_local_model_replacing_a_cloud_seat_is_marked_degraded():
    notes = seats.notes("Implement the export function", "PERSONAL", "qwen", {}, available=set(seats.CHAINS))
    assert any(n.startswith("degraded:") and "claude" in n for n in notes)
    # sensitive work is meant to stay local, so nothing is degraded
    assert not any(n.startswith("degraded:") for n in seats.notes("Implement it", "SENSITIVE", "qwen", {}, available=set(seats.CHAINS)))
    # a cloud seat answering is not degraded
    assert not any(n.startswith("degraded:") for n in seats.notes("Implement it", "PERSONAL", "claude", {}, available=set(seats.CHAINS)))


def test_a_resting_check_seat_gives_check_pending_not_silence():
    resting = {"codex": "usage limit until 2026-11-18 16:02 UTC (no timezone given, read as UTC)"}
    notes = seats.notes("Implement the export function", "PERSONAL", "claude", resting, available=set(seats.CHAINS))
    pending = [n for n in notes if n.startswith("check pending:")]
    assert pending and "codex" in pending[0] and "2026-11-18 16:02 UTC" in pending[0]


def test_the_seat_that_wrote_it_cannot_be_its_own_check():
    notes = seats.notes("Implement the export function", "PERSONAL", "codex", {"claude": "usage limit"}, available=set(seats.CHAINS))
    assert any(n.startswith("check pending:") and "wrote it" in n for n in notes)


def test_no_check_note_when_the_check_seat_is_open_or_not_needed():
    assert seats.notes("Implement the export function", "PERSONAL", "claude", {}, available=set(seats.CHAINS)) == []
    assert seats.notes("Draft a quiz", "PERSONAL", "codex", {"claude": "usage limit"}, available=set(seats.CHAINS)) == []  # L0, no check


def test_the_seat_table_shows_share_rest_and_replacement():
    records = [_run("codex", "failed", error="usage limit. try again at Nov 18th, 2026 4:02 PM UTC"),
               _run("claude", "ok", tokens=12_000)]
    rows = {row["seat"]: row for row in seats.table(records, NOW)}
    assert set(rows) == {"claude", "codex", "gemini", "grok", "qwen", "ollama"}
    assert rows["claude"]["used"] == 12_000 and rows["claude"]["limit"] == 40_000 and rows["claude"]["resting"] == ""
    assert rows["codex"]["resting"].startswith("usage limit until 2026-11-18 16:02 UTC")
    assert rows["codex"]["replacement"] == "claude"
    assert rows["grok"]["replacement"] == "gemini" and rows["qwen"]["replacement"] == "ollama"
    assert rows["qwen"]["limit"] is None  # local seats have no cloud share
    text = seats.render_table(seats.table(records, NOW))
    assert "codex" in text and "resting" in text and "gemini" in text
