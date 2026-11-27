"""`lifeos egress`: what left this laptop. Counts only, per cloud seat: calls, tokens, last call. Never any text."""
import datetime as dt
import json
import shutil

import pytest

from lifeos import egress
from lifeos.cli import main

TODAY = dt.date(2026, 11, 27)


def write_runs(home, records):
    (home / "logs").mkdir(exist_ok=True)
    (home / "logs" / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def rec(model, tokens=1000, status="ok", date="2026-11-26", **extra):
    return {"command": "ask", "model": model, "tokens": tokens, "status": status, "date": date, **extra}


def test_only_cloud_seats_are_counted(tmp_path):
    write_runs(tmp_path, [rec("claude", 1500), rec("codex", 1600), rec("qwen", 9000), rec("ollama:llama3.2", 9000)])
    rows = {r["seat"]: r for r in egress.report(tmp_path, today=TODAY)}
    assert set(rows) == {"claude", "codex"}
    assert rows["claude"]["tokens"] == 1500 and rows["claude"]["calls"] == 1


def test_a_call_that_was_blocked_before_sending_is_not_egress(tmp_path):
    write_runs(tmp_path, [rec("claude", 500, status="blocked"), rec("claude", 700, status="ok")])
    row = egress.report(tmp_path, today=TODAY)[0]
    assert row["calls"] == 1 and row["tokens"] == 700 and row["blocked"] == 1


def test_failed_calls_that_were_sent_still_count_as_sent(tmp_path):
    write_runs(tmp_path, [rec("gemini", 800, status="failed"), rec("gemini", 900)])
    row = egress.report(tmp_path, today=TODAY)[0]
    assert row["calls"] == 2 and row["tokens"] == 1700 and row["failed"] == 1


def test_old_calls_are_outside_the_window(tmp_path):
    write_runs(tmp_path, [rec("grok", 100, date="2026-01-01"), rec("grok", 200, date="2026-11-20")])
    row = egress.report(tmp_path, today=TODAY, days=30)[0]
    assert row["calls"] == 1 and row["last"] == "2026-11-20"


def test_bad_values_never_crash(tmp_path):
    write_runs(tmp_path, [rec("claude", "many"), rec("claude", None), rec("claude", -3), rec("", 5), {"model": "claude"}])
    assert isinstance(egress.report(tmp_path, today=TODAY), list)


def test_no_runs_says_nothing_left(tmp_path):
    assert egress.report(tmp_path, today=TODAY) == []
    assert "nothing" in egress.render([], 30).lower()


def test_the_report_never_contains_text_from_a_run_record(tmp_path):
    write_runs(tmp_path, [rec("claude", 500, prompt="SECRET PROMPT TEXT", answer="SECRET ANSWER TEXT", error="SECRET ERROR")])
    out = egress.render(egress.report(tmp_path, today=TODAY), 30)
    assert "SECRET" not in out


@pytest.fixture
def home(tmp_path, demo, monkeypatch):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    monkeypatch.setenv("LIFEOS_HOME", str(target))
    return target


def test_the_cli_prints_the_table(home, capsys):
    write_runs(home, [rec("codex", 1234, date=dt.date.today().isoformat())])
    assert main(["egress"]) == 0
    out = capsys.readouterr().out
    assert "codex" in out and "1,234" in out
