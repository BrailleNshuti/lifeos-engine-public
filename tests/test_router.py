"""Tests for lifeos/router.py (6-question Section 8.2 routing engine)."""
import json
import shutil

import pytest

from lifeos import router
from lifeos.cli import main


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def test_router_evaluates_six_questions_for_task_and_text(home, capsys):
    dec = router.evaluate_route(home, "T-261116")
    assert len(dec["questions"]) == 6
    assert dec["blocked"] is False
    assert dec["selected_model"] in ("claude", "codex", "qwen", "gemini", "tier0-cli")

    # Confidential work data is blocked at Question 1
    work_dec = router.evaluate_route(home, "Analyze employer client dataset for internal deal")
    assert work_dec["blocked"] is True
    assert work_dec["questions"][0]["verdict"] == "BLOCK_WORK_LANE"

    # Tier-0 script candidate is routed to tier0-cli at Question 2
    t0_dec = router.evaluate_route(home, "Compute weekly numbers and scoreboard math")
    assert t0_dec["blocked"] is False
    assert t0_dec["selected_model"] == "tier0-cli"

    # Sensitive data is forced to local qwen at Question 3 & 4
    sens_dec = router.evaluate_route(home, "Categorize bank csv rows locally")
    assert sens_dec["tier"] == "SENSITIVE"
    assert sens_dec["selected_model"] == "qwen"

    # Secret tier is blocked everywhere
    sec_dec = router.evaluate_route(home, "T-261116", tier="SECRET")
    assert sec_dec["blocked"] is True

    # CLI wiring
    assert main(["--home", str(home), "route", "T-261116", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["target"].endswith("T-261116-demo-cli.md")
    assert main(["--home", str(home), "route", "T-261116", "--tier", "SECRET"]) == 1
