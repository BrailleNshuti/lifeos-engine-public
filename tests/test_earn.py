import datetime as dt
import json

from lifeos import earn
from lifeos.cli import main

TODAY = dt.date(2026, 11, 18)


def csv_log(home, name, header, rows):
    d = home / "logs"
    d.mkdir(exist_ok=True)
    (d / name).write_text(header + "\n" + "".join(r + "\n" for r in rows), encoding="utf-8")


def test_parts_with_recent_use_keep_their_place_and_idle_ones_are_flagged(tmp_path):
    csv_log(tmp_path, "ratings.csv", "date,task,model,score,kind,note", ["2026-11-10,T,claude,4,code,"])
    csv_log(tmp_path, "vocab.csv", "date,word,kind,value,text", ["2026-08-01,Haus,add,,"])
    rows = {r["part"]: r for r in earn.review(tmp_path, today=TODAY, days=30)}
    assert rows["rate / learn"]["uses"] == 1 and rows["rate / learn"]["verdict"] == "earns its place"
    assert rows["vocab"]["uses"] == 0 and rows["vocab"]["last"] == "2026-08-01" and rows["vocab"]["verdict"] == "quiet: pause or remove?"
    assert rows["experiment"]["last"] == "-" and rows["experiment"]["verdict"] == "never used: pause or remove?"


def test_runs_and_decisions_are_counted(tmp_path):
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "runs.jsonl").write_text(
        json.dumps({"command": "panel", "date": "2026-11-15"}) + "\n" + json.dumps({"command": "ask", "date": "2026-11-16"}) + "\n", encoding="utf-8")
    (tmp_path / "decisions").mkdir()
    (tmp_path / "decisions" / "D-261117-x.md").write_text("---\ndate: 2026-11-17\n---\n", encoding="utf-8")
    rows = {r["part"]: r for r in earn.review(tmp_path, today=TODAY)}
    assert rows["ask / delegate / panel"]["uses"] == 2 and rows["decide"]["uses"] == 1


def test_debate_answers_earn_their_own_row_and_do_not_inflate_ask(tmp_path):
    (tmp_path / "logs").mkdir()
    records = [
        {"command": "ask", "date": "2026-11-15"},
        {"command": "debate", "date": "2026-11-16", "round": 0, "source": "start", "status": "ok"},        # a start is not a use
        {"command": "debate", "date": "2026-11-16", "round": 1, "source": "run", "status": "ok"},
        {"command": "debate", "date": "2026-11-16", "round": 1, "source": "run", "status": "tool_missing"},  # a skipped seat is not a use
        {"command": "debate", "date": "2026-11-17", "round": 2, "source": "manual", "status": "ok"},
    ]
    (tmp_path / "logs" / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    rows = {r["part"]: r for r in earn.review(tmp_path, today=TODAY)}
    assert rows["ask / delegate / panel"]["uses"] == 1
    assert rows["debate"]["uses"] == 2 and rows["debate"]["last"] == "2026-11-17" and rows["debate"]["verdict"] == "earns its place"


def test_a_debate_never_run_is_flagged(tmp_path):
    rows = {r["part"]: r for r in earn.review(tmp_path, today=TODAY)}
    assert rows["debate"]["uses"] == 0 and rows["debate"]["verdict"] == "never used: pause or remove?"


def test_damaged_logs_do_not_crash(tmp_path):
    csv_log(tmp_path, "ledger.csv", "date,task,model,minutes_saved,note", ["garbage", ",,,,", "2026-11-17,T,m,5,"])
    assert {r["part"]: r for r in earn.review(tmp_path, today=TODAY)}["ledger"]["uses"] == 1


def test_cli(tmp_path, capsys):
    (tmp_path / "now.md").write_text("# now\n", encoding="utf-8")
    assert main(["--home", str(tmp_path), "earn"]) == 0
    assert "never used" in capsys.readouterr().out
