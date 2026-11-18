import datetime as dt
import shutil

import pytest

from lifeos import cli, governor
from lifeos.cli import main
from lifeos.store import append_run_record

NOW = dt.datetime(2026, 11, 20, 12, 0, tzinfo=dt.timezone.utc)


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def spend(home, model, tokens, n=1, status="ok", error=None, finished="2026-11-20T10:00:00Z"):
    for i in range(n):
        rec = {"run_id": f"R-{model}-{tokens}-{i}-{status}", "command": "ask", "status": status, "model": model,
               "tokens": tokens, "budget": 6000, "full": False, "parent_run_id": None, "date": "2026-11-20",
               "started_at": finished, "finished_at": finished}
        if error:
            rec["error"] = error
        append_run_record(home, rec)


def test_a_fresh_week_allows_every_seat(home):
    out = governor.check(home, "codex", 1500, now=NOW)
    assert out["allowed"] and out["reasons"] == [] and out["week"]["used_tokens"] == 0


def test_local_seats_never_touch_the_cloud_budget(home):
    spend(home, "claude", 40_000, n=3)
    out = governor.check(home, "qwen", 9000, now=NOW)
    assert out["allowed"] and "laptop" in out["note"]


def test_a_spent_week_holds_cloud_seats(home):
    spend(home, "claude", 40_000, n=3)
    out = governor.check(home, "codex", 1000, now=NOW)
    assert not out["allowed"] and any("weekly" in r for r in out["reasons"])


def test_a_call_that_would_cross_the_cap_is_held_before_it_is_sent(home):
    spend(home, "claude", 39_000, n=1)
    spend(home, "codex", 39_000, n=1)
    spend(home, "gemini", 30_000, n=1)
    out = governor.check(home, "claude", 5000, now=NOW)
    assert not out["allowed"] and any("would" in r for r in out["reasons"])


def test_a_seat_resting_after_a_usage_limit_is_held(home):
    spend(home, "codex", 100, status="failed", error="You've hit your usage limit. try again at 2026-11-21 16:02")
    out = governor.check(home, "codex", 500, now=NOW)
    assert not out["allowed"] and any("usage limit" in r for r in out["reasons"])


def test_cli_holds_a_spent_seat_and_force_overrides(home, capsys, monkeypatch):
    spend(home, "claude", 40_000, n=3)
    monkeypatch.setenv("LIFEOS_HOME", str(home))
    called = []
    monkeypatch.setattr(cli, "run_ask", lambda *a, **k: called.append(a) or home / "tasks" / "x.md")
    assert main(["ask", "codex", "T-261116"]) == 4
    assert called == [] and "budget governor" in capsys.readouterr().err
    main(["ask", "codex", "T-261116", "--force"])
    assert len(called) == 1


def test_cli_dry_run_reports_but_does_not_hold(home, capsys, monkeypatch):
    spend(home, "claude", 40_000, n=3)
    monkeypatch.setenv("LIFEOS_HOME", str(home))
    assert main(["ask", "codex", "T-261116", "--dry-run"]) == 0
    assert "budget governor" in capsys.readouterr().err
