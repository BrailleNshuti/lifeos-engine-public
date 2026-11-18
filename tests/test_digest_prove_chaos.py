import datetime as dt
import json
import shutil

import pytest

from lifeos import calibrate, digest, learn, prove, vocab
from lifeos.cli import main
from lifeos.store import append_csv_row, read_run_records
from lifeos.verify import verify_chain

D = dt.date(2026, 11, 29)


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def test_digest_marks_unused_parts_for_the_rule_10_question(home):
    calibrate.predict(home, "it ships", 70, today=D)
    vocab.add(home, "das Haus", "house", today=dt.date(2026, 10, 1))
    d = digest.build(home, today=D)
    parts = {p["part"]: p for p in d["parts"]}
    assert parts["predictions"]["week"] == 1 and parts["predictions"]["verdict"] == "earned its place"
    assert parts["vocabulary"]["week"] == 0 and "pause or remove" in parts["vocabulary"]["verdict"]
    assert "Sunday review" in digest.render(d)


def test_digest_on_an_empty_home_does_not_crash(home):
    assert digest.build(home, today=D)["parts"]


def test_prove_reports_each_check_and_fails_when_one_fails(home, tmp_path):
    out = prove.run(home, run_tests=False, today=D)
    names = [c["name"] for c in out["checks"]]
    assert {"ledger chain", "guard score", "outbound stop"} <= set(names)
    assert out["ok"] and "Proof · 2026-11-29" in prove.render(out)
    (home / "logs" / "runs.jsonl").write_text('{"a": 1}\n{"b": 2, "prev_hash": "' + "f" * 64 + '"}\n')
    assert not prove.run(home, run_tests=False, today=D)["ok"]


def test_cli_prove_and_digest(home, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LIFEOS_HOME", str(home))
    out = tmp_path / "proof.md"
    assert main(["prove", "--skip-tests", "--out", str(out)]) == 0
    assert "Proof" in out.read_text(encoding="utf-8")
    assert main(["digest"]) == 0
    assert "Sunday review" in capsys.readouterr().out


# ---- chaos: damage the files and check the engine stays honest ----

def test_torn_last_line_is_reported_not_fatal(home):
    log = home / "logs" / "runs.jsonl"
    log.parent.mkdir(exist_ok=True)
    log.write_text('{"run_id": "r1", "model": "claude"}\n{"run_id": "x", "model": "cla')
    assert isinstance(read_run_records(home), list)
    assert verify_chain(home)["errors"]


def test_crlf_checkout_keeps_the_chain_valid(home, monkeypatch):
    from lifeos import ask
    ask.run_ask(home, "claude", "T-261116", adapters={"claude": lambda p: "ok"}, today=D)
    ask.run_ask(home, "claude", "T-261116", adapters={"claude": lambda p: "ok"}, today=D)
    log = home / "logs" / "runs.jsonl"
    log.write_bytes(log.read_bytes().replace(b"\n", b"\r\n"))
    assert verify_chain(home)["ok"]


def test_csv_without_final_newline_is_repaired_on_append(home):
    learn.add_rating(home, "T-261116", "claude", 4, "implement a python module", today=D)
    path = home / "logs" / "ratings.csv"
    path.write_bytes(path.read_bytes().rstrip(b"\n"))
    learn.add_rating(home, "T-261116", "codex", 5, "implement a python module", today=D)
    assert len(learn.read_ratings(home)) == 2


def test_garbage_rows_are_skipped_not_fatal(home):
    learn.add_rating(home, "T-261116", "claude", 4, "implement a python module", today=D)
    path = home / "logs" / "ratings.csv"
    path.write_text(path.read_text(encoding="utf-8") + "garbage\n2026-11-29,T-1,claude,not-a-number,k,\n")
    assert len(learn.read_ratings(home)) == 1
    assert calibrate.report(home)["resolved"] == 0
