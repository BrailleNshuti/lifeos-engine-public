"""Tests for lifeos/runs.py and `lifeos runs` CLI."""
import datetime as dt
import json
import shutil

import pytest

from lifeos import ask, runs
from lifeos.cli import main

TODAY = dt.date(2026, 11, 20)
CLEAN = "Updated tests/test_runs.py and verified output. Next step: run pytest."


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def test_runs_summary_and_filters(home, capsys):
    ask.run_ask(home, "claude", "T-261116", adapters={"claude": lambda p: CLEAN}, today=TODAY, run_id="R-test-1")
    ask.run_ask(home, "codex", "T-261116", adapters={"codex": lambda p: CLEAN}, today=TODAY, run_id="R-test-2")
    with pytest.raises(ask.AskError):
        ask.run_ask(
            home, "codex", "T-261116",
            adapters={"codex": lambda p: (_ for _ in ()).throw(ask.AskError("provider down"))},
            today=TODAY, run_id="R-test-3",
        )

    summary = runs.summarize_runs(home)
    assert summary["total_matching"] == 3
    assert summary["by_status"] == {"failed": 1, "ok": 2}
    assert summary["by_model"] == {"codex": 2, "claude": 1}
    assert [r["run_id"] for r in summary["runs"]] == ["R-test-3", "R-test-2", "R-test-1"]

    failed_only = runs.summarize_runs(home, status="failed")
    assert failed_only["total_matching"] == 1
    assert failed_only["runs"][0]["run_id"] == "R-test-3"

    claude_only = runs.summarize_runs(home, model="claude")
    assert claude_only["total_matching"] == 1
    assert claude_only["runs"][0]["run_id"] == "R-test-1"

    assert main(["--home", str(home), "runs", "--limit", "2", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total_matching"] == 3
    assert payload["shown"] == 2

    assert main(["--home", str(home), "runs", "--status", "ok"]) == 0
    text = capsys.readouterr().out
    assert "Runs: 2 total" in text
    assert "R-test-2" in text and "R-test-1" in text


def test_duration_comes_from_duration_ms(home):
    """Run records store milliseconds; the audit must still show seconds."""
    ask.run_ask(home, "claude", "T-261116", adapters={"claude": lambda p: CLEAN}, today=TODAY, run_id="R-dur-1")
    rec = runs.filter_runs(home)[0]
    assert isinstance(rec["duration_ms"], int)
    assert rec["duration_s"] == round(rec["duration_ms"] / 1000, 3)
    assert runs.summarize_runs(home)["avg_duration_s"] is not None
    assert runs.render_runs(runs.summarize_runs(home)).count("n/a") == 0
