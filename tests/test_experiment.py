import csv
import datetime as dt
import json
import shutil

import pytest

from lifeos import experiment
from lifeos.cli import main

START = dt.date(2026, 12, 1)
DAYS = 14


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def ledger(home, rows):
    path = home / "logs" / "ledger.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["date", "task", "model", "minutes_saved", "note"])
        for d, m in rows:
            w.writerow([d.isoformat(), "T-1", "claude", m, ""])


def days_before(n):
    return START - dt.timedelta(days=n)


def test_start_records_the_baseline_and_only_one_experiment_runs_at_a_time(home):
    ledger(home, [(days_before(3), 30), (days_before(8), 30)])
    e = experiment.start(home, "Block 1 starts with the hardest task", "minutes_saved", days=DAYS, today=START)
    assert e["id"] == "E-001" and e["baseline"] == 30.0  # 60 minutes over two weeks = 30 per week
    with pytest.raises(experiment.ExperimentError, match="already running"):
        experiment.start(home, "another change", "minutes_saved", today=START)


def test_unknown_metric_and_private_text_are_refused(home):
    with pytest.raises(experiment.ExperimentError):
        experiment.start(home, "x", "vibes", today=START)
    with pytest.raises(experiment.ExperimentError):
        experiment.start(home, "key sk-ant-api03-" + "a1B2c3D4" * 5, "minutes_saved", today=START)


def test_a_clear_improvement_is_kept(home):
    ledger(home, [(days_before(3), 30), (days_before(8), 30)])
    e = experiment.start(home, "change", "minutes_saved", days=DAYS, today=START)
    ledger(home, [(days_before(3), 30), (days_before(8), 30)] + [(START + dt.timedelta(days=i), 40) for i in range(1, 5)])
    out = experiment.end(home, e["id"], today=START + dt.timedelta(days=DAYS))
    assert out["verdict"] == "keep" and out["after"] > out["baseline"]


def test_no_improvement_is_reverted_because_only_improvements_are_kept(home):
    ledger(home, [(days_before(3), 60), (days_before(8), 60)])
    e = experiment.start(home, "change", "minutes_saved", days=DAYS, today=START)
    ledger(home, [(days_before(3), 60), (days_before(8), 60)] + [(START + dt.timedelta(days=i), 15) for i in range(1, 5)])
    out = experiment.end(home, e["id"], today=START + dt.timedelta(days=DAYS))
    assert out["verdict"] == "revert"


def test_too_few_data_points_is_inconclusive_not_a_verdict(home):
    ledger(home, [(days_before(3), 30)])
    e = experiment.start(home, "change", "minutes_saved", days=DAYS, today=START)
    ledger(home, [(START + dt.timedelta(days=1), 99)])
    out = experiment.end(home, e["id"], today=START + dt.timedelta(days=DAYS))
    assert out["verdict"] == "inconclusive" and "extend" in out["why"]


def test_cannot_end_before_the_trial_has_run_its_days(home):
    ledger(home, [(days_before(3), 30)])
    e = experiment.start(home, "change", "minutes_saved", days=DAYS, today=START)
    with pytest.raises(experiment.ExperimentError, match="not finished"):
        experiment.end(home, e["id"], today=START + dt.timedelta(days=3))


def test_lower_is_better_for_failure_rate(home):
    log = home / "logs" / "runs.jsonl"
    log.parent.mkdir(exist_ok=True)

    def runs(rows):
        log.write_text("".join(json.dumps({"command": "ask", "model": "claude", "date": d.isoformat(), "status": s}) + "\n"
                               for d, s in rows))
    base = [(days_before(i), "failed" if i % 2 else "ok") for i in range(1, 8)]
    runs(base)
    e = experiment.start(home, "smaller packs", "failed_rate", days=DAYS, today=START)
    runs(base + [(START + dt.timedelta(days=i), "ok") for i in range(1, 7)])
    assert experiment.end(home, e["id"], today=START + dt.timedelta(days=DAYS))["verdict"] == "keep"


def test_list_and_cli(home, capsys, monkeypatch):
    monkeypatch.setenv("LIFEOS_HOME", str(home))
    assert main(["experiment", "start", "Hardest task first", "--metric", "minutes_saved", "--days", "14"]) == 0
    assert main(["experiment", "start", "second", "--metric", "minutes_saved"]) == 2
    assert main(["experiment", "end", "E-001"]) == 2  # not finished yet
    assert main(["experiment", "list"]) == 0
    assert "E-001" in capsys.readouterr().out
