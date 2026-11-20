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


def test_main_runs_the_given_command_n_times(tmp_path):
    rc = soak.main(["--runs", "2", "--cmd", "python -c pass", "--diag", str(tmp_path / "d.jsonl")])
    assert rc == 0
