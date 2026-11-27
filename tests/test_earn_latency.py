"""`lifeos earn` also shows, per seat, how long calls took and how many failed (from the run ledger, no model call)."""
import datetime as dt
import json
import shutil

from lifeos import earn
from lifeos.cli import main

TODAY = dt.date(2026, 11, 27)


def write_runs(home, records):
    (home / "logs").mkdir(exist_ok=True)
    (home / "logs" / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def rec(model, ms, status="ok", date="2026-11-26", command="ask"):
    return {"command": command, "model": model, "duration_ms": ms, "status": status, "date": date}


def test_median_worst_and_failures_per_seat(tmp_path):
    write_runs(tmp_path, [rec("gemini", 50000), rec("gemini", 56000), rec("gemini", 90000), rec("gemini", 0, "failed"),
                          rec("codex", 31000), rec("grok", 29000)])
    rows = {r["seat"]: r for r in earn.latency(tmp_path, today=TODAY, days=30)}
    assert rows["gemini"] == {"seat": "gemini", "ok": 3, "failed": 1, "median_s": 56.0, "worst_s": 90.0}
    assert rows["codex"]["median_s"] == 31.0 and rows["codex"]["failed"] == 0


def test_a_failed_call_does_not_count_toward_the_median(tmp_path):
    write_runs(tmp_path, [rec("claude", 10000), rec("claude", 600000, "failed")])
    row = earn.latency(tmp_path, today=TODAY)[0]
    assert row["median_s"] == 10.0 and row["worst_s"] == 10.0 and row["failed"] == 1


def test_model_names_with_a_tag_are_grouped_by_seat(tmp_path):
    write_runs(tmp_path, [rec("ollama:llama3.2", 78000), rec("ollama", 22000)])
    rows = earn.latency(tmp_path, today=TODAY)
    assert [r["seat"] for r in rows] == ["ollama"] and rows[0]["ok"] == 2


def test_old_runs_and_records_without_a_duration_are_left_out(tmp_path):
    write_runs(tmp_path, [rec("grok", 1000, date="2026-01-01"), {"command": "ask", "model": "grok", "status": "ok",
                                                             "date": "2026-11-26"}, rec("grok", 2000)])
    rows = earn.latency(tmp_path, today=TODAY, days=30)
    assert rows[0]["ok"] == 1 and rows[0]["median_s"] == 2.0


def test_no_runs_gives_no_rows_and_no_crash(tmp_path):
    assert earn.latency(tmp_path, today=TODAY) == []
    assert "no timed calls" in earn.render_latency([]).lower()


def test_garbage_values_do_not_crash(tmp_path):
    write_runs(tmp_path, [rec("grok", "slow"), rec("grok", None), rec("grok", -5), rec("", 100), rec("grok", 4000)])
    rows = earn.latency(tmp_path, today=TODAY)
    assert rows and rows[0]["seat"] == "grok" and rows[0]["median_s"] == 4.0


def test_the_table_is_readable(tmp_path):
    write_runs(tmp_path, [rec("codex", 31000)])
    text = earn.render_latency(earn.latency(tmp_path, today=TODAY))
    assert "codex" in text and "31.0" in text and "median" in text.lower()


def test_cli_earn_prints_the_latency_table(tmp_path, demo, capsys, monkeypatch):
    home = tmp_path / "home"
    shutil.copytree(demo, home)
    write_runs(home, [rec("codex", 31000, date=dt.date.today().isoformat())])
    monkeypatch.setenv("LIFEOS_HOME", str(home))
    assert main(["earn"]) == 0
    out = capsys.readouterr().out
    assert "Did each part earn its place" in out and "codex" in out and "median" in out.lower()
