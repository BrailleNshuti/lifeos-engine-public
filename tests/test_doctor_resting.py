"""`doctor` names the seats that are resting after a usage limit (round 4 item 15). Made-up ledger only."""
import datetime as dt
import json

from lifeos.cli import main


def make_home(tmp_path):
    (tmp_path / "logs").mkdir()
    (tmp_path / "now.md").write_text("# now", encoding="utf-8")
    return tmp_path


def test_a_seat_that_hit_its_usage_limit_is_named(tmp_path, capsys):
    home = make_home(tmp_path)
    now = dt.datetime.now(dt.timezone.utc)
    rec = {"command": "ask", "model": "codex", "status": "failed", "date": now.date().isoformat(),
           "started_at": now.isoformat().replace("+00:00", "Z"), "finished_at": now.isoformat().replace("+00:00", "Z"),
           "error": "You've hit your usage limit. Try again later.", "tokens": 0}
    (home / "logs" / "runs.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
    main(["--home", str(home), "doctor"])
    assert "resting   codex: usage limit until" in capsys.readouterr().out


def test_no_resting_line_when_nothing_rests(tmp_path, capsys):
    home = make_home(tmp_path)
    main(["--home", str(home), "doctor"])
    assert "  resting   " not in capsys.readouterr().out


def test_a_broken_ledger_never_stops_doctor(tmp_path, capsys):
    home = make_home(tmp_path)
    (home / "logs" / "runs.jsonl").write_bytes(b"\xff\xfe not json\n{\n")
    main(["--home", str(home), "doctor"])
    assert "LifeOS home" in capsys.readouterr().out
