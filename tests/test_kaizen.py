"""Tests for lifeos/kaizen.py (Monthly System Health & 4-week trial check)."""
import datetime as dt
import json
import shutil

import pytest

from lifeos import ask, kaizen
from lifeos.cli import main

TODAY = dt.date(2026, 11, 20)
CLEAN = "Implemented feature and verified tests. Next step: merge."


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def test_system_health_computes_five_questions_and_trials(home):
    # Create a system/changes.md with one 30-day-old trial due for verdict and one fresh trial
    sys_dir = home / "system"
    sys_dir.mkdir(exist_ok=True)
    (sys_dir / "changes.md").write_text(
        "# System changes\n"
        "| date | change | reason | metric | baseline | result after 4 weeks | KEEP or REVERT |\n"
        "|---|---|---|---|---|---|---|\n"
        "| 2026-10-15 | Short context packs | save tokens | tokens/call | 4000 | - | - |\n"
        "| 2026-11-12 | Sonnet default | weekly limit | limit % | 96% | - | - |\n",
        encoding="utf-8",
    )
    ask.run_ask(home, "claude", "T-261116", adapters={"claude": lambda p: CLEAN}, today=TODAY, run_id="R-kzn-1")
    ask.run_ask(home, "claude", "T-261116", adapters={"claude": lambda p: CLEAN}, today=TODAY, run_id="R-kzn-2")

    report = kaizen.system_health(home, month="2026-11", today=TODAY)
    assert report["month"] == "2026-11"
    assert report["routing_waste"]["total_runs"] == 2
    assert report["routing_waste"]["calls_by_model"] == {"claude": 2}
    # T-261116-demo-cli appears multiple times in ledger -> Tier 0 candidate
    assert any(c["task"] == "T-261116-demo-cli" for c in report["tier0_candidates"])
    assert report["weakest_area"]["area"] in ("german", "lab", "study", "work")
    due = [t for t in report["pending_trials"] if t["due_for_verdict"]]
    assert len(due) == 1 and due[0]["change"] == "Short context packs"

    md = kaizen.render_system_health(report)
    assert "# System Health · 2026-11" in md
    assert "1. Routing waste" in md
    assert "2. Move to Tier 0 for good:" in md
    assert "3. The one change that helps most:" in md
    assert "4. Weakest area and the smallest experiment:" in md
    assert "5. Unused or heaviest part / 4-week trial check:" in md
    assert "Short context packs" in md


def test_kaizen_cli_draft_and_json_and_no_overwrite(home, capsys):
    assert main(["--home", str(home), "kaizen", "--month", "2026-11", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["month"] == "2026-11"

    assert main(["--home", str(home), "kaizen", "--month", "2026-11", "--draft"]) == 0
    out_rel = capsys.readouterr().out.strip().replace("\\", "/")
    assert out_rel == "reviews/2026-11.md"
    assert (home / "reviews" / "2026-11.md").exists()

    # Second draft call must refuse to overwrite
    assert main(["--home", str(home), "kaizen", "--month", "2026-11", "--draft"]) == 2
    assert "already exists" in capsys.readouterr().err
