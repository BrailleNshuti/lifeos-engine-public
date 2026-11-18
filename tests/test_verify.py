import datetime as dt
import json
import shutil

import pytest

from lifeos import ask, verify
from lifeos.cli import main

TODAY = dt.date(2026, 11, 20)
CLEAN = "Updated tests/test_runs.py and verified output. Next step: run pytest."


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def add_runs(home, n, start=1):
    for i in range(start, start + n):
        ask.run_ask(home, "claude", "T-261116", adapters={"claude": lambda p: CLEAN}, today=TODAY, run_id=f"R-chain-{i}")


def runs_lines(home):
    return (home / "logs" / "runs.jsonl").read_bytes().split(b"\n")


def write_lines(home, lines):
    (home / "logs" / "runs.jsonl").write_bytes(b"\n".join(lines))


def test_new_records_form_a_chain(home):
    add_runs(home, 3)
    result = verify.verify_chain(home)
    assert result["ok"] and result["records"] == 3 and result["chained"] == 3 and result["legacy"] == 0
    recs = [json.loads(l) for l in runs_lines(home) if l.strip()]
    assert recs[0]["prev_hash"] == "0" * 64
    assert recs[1]["prev_hash"] == verify.line_hash(runs_lines(home)[0])
    assert len(result["head"]) == 64


def test_empty_or_missing_log_is_fine(home):
    result = verify.verify_chain(home)
    assert result["ok"] and result["records"] == 0 and result["head"] == "0" * 64


def test_legacy_records_before_the_chain_are_counted_not_failed(home):
    legacy = [json.dumps({"run_id": f"old-{i}", "status": "ok", "command": "ask", "date": "2026-11-10"}, sort_keys=True).encode()
              for i in range(2)]
    (home / "logs" / "runs.jsonl").write_bytes(b"\n".join(legacy) + b"\n")
    add_runs(home, 2)
    result = verify.verify_chain(home)
    assert result["ok"] and result["legacy"] == 2 and result["chained"] == 2


def test_editing_a_middle_record_is_detected(home):
    add_runs(home, 3)
    lines = runs_lines(home)
    rec = json.loads(lines[1]); rec["status"] = "failed"
    lines[1] = json.dumps(rec, sort_keys=True).encode()
    write_lines(home, lines)
    result = verify.verify_chain(home)
    assert not result["ok"] and any("line 3" in e for e in result["errors"])


def test_deleting_a_middle_record_is_detected(home):
    add_runs(home, 3)
    lines = runs_lines(home)
    del lines[1]
    write_lines(home, lines)
    assert not verify.verify_chain(home)["ok"]


def test_reordering_records_is_detected(home):
    add_runs(home, 3)
    lines = runs_lines(home)
    lines[0], lines[1] = lines[1], lines[0]
    write_lines(home, lines)
    assert not verify.verify_chain(home)["ok"]


def test_an_unchained_record_after_the_chain_started_is_detected(home):
    add_runs(home, 2)
    extra = json.dumps({"run_id": "sneaky", "status": "ok", "command": "ask"}, sort_keys=True).encode()
    (home / "logs" / "runs.jsonl").write_bytes((home / "logs" / "runs.jsonl").read_bytes() + extra + b"\n")
    result = verify.verify_chain(home)
    assert not result["ok"] and any("not chained" in e for e in result["errors"])


def test_editing_the_last_record_is_caught_by_a_saved_anchor(home):
    add_runs(home, 2)
    anchor = verify.verify_chain(home)["head"]
    add_runs(home, 1, start=3)
    assert verify.verify_chain(home, anchor=anchor)["anchor_found"] is True
    lines = runs_lines(home)
    rec = json.loads(lines[1]); rec["model"] = "someone-else"
    lines[1] = json.dumps(rec, sort_keys=True).encode()
    write_lines(home, lines)
    result = verify.verify_chain(home, anchor=anchor)
    assert not result["ok"] or result["anchor_found"] is False


def test_truncating_the_tail_is_caught_by_a_saved_anchor(home):
    add_runs(home, 3)
    anchor = verify.verify_chain(home)["head"]
    write_lines(home, runs_lines(home)[:2])
    result = verify.verify_chain(home, anchor=anchor)
    assert result["anchor_found"] is False


def test_crlf_line_endings_do_not_break_the_chain(home):
    add_runs(home, 3)
    path = home / "logs" / "runs.jsonl"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert verify.verify_chain(home)["ok"]


def test_cli_verify_exit_codes(home, capsys, monkeypatch):
    add_runs(home, 2)
    monkeypatch.setenv("LIFEOS_HOME", str(home))
    assert main(["verify"]) == 0
    assert "chain ok" in capsys.readouterr().out
    lines = runs_lines(home)
    rec = json.loads(lines[0]); rec["status"] = "failed"
    lines[0] = json.dumps(rec, sort_keys=True).encode()
    write_lines(home, lines)
    assert main(["verify"]) == 1
    assert "BROKEN" in capsys.readouterr().out
