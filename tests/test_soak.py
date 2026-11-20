"""scripts/soak.py: counts recovered and failed os.replace events over repeated full test runs."""
import importlib.util
import json
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("soak", Path(__file__).resolve().parent.parent / "scripts" / "soak.py")
soak = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(soak)


def test_count_events_counts_each_kind_and_skips_junk(tmp_path):
    f = tmp_path / "diag.jsonl"
    lines = [json.dumps({"event": "os.replace recovered"}), "not json", json.dumps({"event": "os.replace failed"}),
             json.dumps({"event": "os.replace recovered"}), json.dumps(["list"]), json.dumps({"event": "other"})]
    f.write_text("\n".join(lines), encoding="utf-8")
    assert soak.count_events(f) == {"recovered": 2, "failed": 1}


def test_count_events_missing_file_is_zero(tmp_path):
    assert soak.count_events(tmp_path / "none.jsonl") == {"recovered": 0, "failed": 0}


def test_summary_line_reports_totals_and_exit_codes():
    runs = [{"code": 0, "recovered": 2, "failed": 0}, {"code": 1, "recovered": 0, "failed": 1}, {"code": 0, "recovered": 1, "failed": 0}]
    text = soak.summary(runs)
    assert "3 runs" in text and "2 passed" in text and "recovered 3" in text and "failed 1" in text


def test_main_runs_the_command_n_times_and_counts_new_events_per_run(tmp_path, monkeypatch, capsys):
    diag = tmp_path / "d.jsonl"
    calls = []
    codes = iter([0, 1])

    def fake_run(cmd, shell, env):
        calls.append((cmd, env["LIFEOS_REPLACE_DIAG"]))
        with open(diag, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": "os.replace recovered"}) + "\n")
        return type("R", (), {"returncode": next(codes)})()

    monkeypatch.setattr(soak.subprocess, "run", fake_run)
    rc = soak.main(["--runs", "2", "--cmd", "suite", "--diag", str(diag)])
    out = capsys.readouterr().out
    assert rc == 1 and len(calls) == 2 and calls[0] == ("suite", str(diag))
    assert "run 1: exit 0, recovered 1, failed 0" in out and "run 2: exit 1, recovered 1, failed 0" in out
    assert "2 runs, 1 passed, os.replace recovered 2" in out


def test_zero_or_negative_runs_are_refused():
    import pytest
    for bad in ("0", "-1"):
        with pytest.raises(SystemExit):
            soak.main(["--runs", bad])


def test_unusable_diag_path_exits_nonzero_instead_of_reporting_zero(tmp_path, capsys):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    assert soak.main(["--runs", "1", "--cmd", "suite", "--diag", str(blocker / "sub" / "d.jsonl")]) == 2
    assert "cannot use the diagnostics file" in capsys.readouterr().err


def test_default_diag_log_is_removed_afterwards(monkeypatch):
    seen = []
    monkeypatch.setattr(soak.subprocess, "run", lambda cmd, shell, env: seen.append(env["LIFEOS_REPLACE_DIAG"]) or type("R", (), {"returncode": 0})())
    assert soak.main(["--runs", "1", "--cmd", "suite"]) == 0
    assert not Path(seen[0]).exists()
