import datetime as dt
import json
import shutil

import pytest

from lifeos import ask
from lifeos.cli import main
from lifeos.week import render_markdown, week_bounds, week_numbers

TODAY = dt.date(2026, 11, 20)  # a Friday in 2026-W47, the demo week
HEDGY = "All done, it works. I think it should work, probably; next step: none."  # 2 flags
CLEAN = "Added the check in lifeos/ask.py and tests/test_ask.py. Next step: review the diff."  # 0 flags


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def ask_with(home, model, answer):
    """One lifeos ask call with a fake adapter: no network, no command-line tool."""
    ask.run_ask(home, model, "T-261116", adapters={model: lambda prompt: answer}, today=TODAY)


def test_week_bounds():
    start, end = week_bounds("2026-W47")
    assert (start.isoformat(), end.isoformat()) == ("2026-11-16", "2026-11-22")


def test_week_numbers_come_only_from_the_logs(demo):
    n = week_numbers(demo, "2026-W47")
    assert n["proofs"] == 3 and n["proofs_by_area"] == {"career": 2, "german": 1}
    assert n["ledger_lines"] == 3 and n["net_hours_saved"] == 1.0
    assert "Proofs: 3 (career 2, german 1)" in render_markdown(n)


def test_empty_week_says_none(demo):
    assert "none this week" in render_markdown(week_numbers(demo, "2026-W40"))


def test_delegation_line_counts_calls_per_model_and_flagged_answers(home):
    ask_with(home, "claude", CLEAN)
    ask_with(home, "claude", HEDGY)
    ask_with(home, "codex", CLEAN)
    n = week_numbers(home, "2026-W47")
    assert n["delegation"] == {"calls": 3, "by_model": {"claude": 2, "codex": 1}, "flagged": 1}
    assert "Delegation: 3 calls (claude 2, codex 1); flagged answers: 1 of 3" in render_markdown(n)


def test_most_used_model_comes_first(home):
    for model in ("claude", "codex", "codex"):
        ask_with(home, model, CLEAN)
    assert "(codex 2, claude 1)" in render_markdown(week_numbers(home, "2026-W47"))


def test_a_week_without_model_calls_says_none(demo):
    for week in ("2026-W47", "2026-W40"):  # W47 has ledger lines but no lifeos ask; W40 has no lines at all
        n = week_numbers(demo, week)
        assert n["delegation"] == {"calls": 0, "by_model": {}, "flagged": 0}
        assert "Delegation: none this week" in render_markdown(n)


def test_json_has_the_delegation_keys_and_the_old_ones(home, capsys):
    ask_with(home, "claude", HEDGY)
    assert main(["--home", str(home), "week", "--week", "2026-W47", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["delegation"] == {"calls": 1, "by_model": {"claude": 1}, "flagged": 1}
    assert {"week", "from", "to", "ledger_lines", "net_hours_saved", "proofs", "proofs_by_area", "proof_links"} <= set(data)


def test_old_ledger_lines_without_flags_still_parse(home):
    with open(home / "logs" / "ledger.csv", "a", encoding="utf-8") as f:
        f.write("2026-11-19,T-261116-demo-cli,claude,,asked via lifeos ask\n"  # written before flags existed
                "2026-11-19,T-261116-demo-cli,codex,,asked via lifeos ask; flags: 1\n"
                "2026-11-19,T-261116-demo-cli,chat,,written via lifeos mcp\n"  # not a model call
                "2026-11-25,T-261116-demo-cli,claude,,asked via lifeos ask; flags: 3\n")  # another week
    n = week_numbers(home, "2026-W47")
    assert n["delegation"] == {"calls": 2, "by_model": {"claude": 1, "codex": 1}, "flagged": 1}
    assert "Delegation: 2 calls (claude 1, codex 1); flagged answers: 1 of 2" in render_markdown(n)


def test_cli_prints_the_delegation_line_after_the_numbers(home, capsys):
    ask_with(home, "claude", CLEAN)
    assert main(["--home", str(home), "week", "--week", "2026-W47"]) == 0
    out = capsys.readouterr().out
    line = "Delegation: 1 calls (claude 1); flagged answers: 0 of 1"
    assert out.index("Net time saved") < out.index(line) < out.index("## Proof links")


def test_a_week_in_the_wrong_format_gives_a_usage_hint(home, capsys):
    assert main(["--home", str(home), "week", "--week", "2026-47"]) != 0
    err = capsys.readouterr().err
    assert "2026-W47" in err and "Traceback" not in err


def test_week_includes_logged_hours_and_health_when_present(home):
    assert main(["--home", str(home), "log", "hours", "--area", "study", "--hours", "2.5", "--date", "2026-11-18"]) == 0
    assert main(["--home", str(home), "log", "hours", "--area", "german", "--hours", "1.5", "--date", "2026-11-19"]) == 0
    assert main([
        "--home", str(home), "log", "health",
        "--sleep", "7.5", "--gym", "yes", "--energy", "4", "--date", "2026-11-18",
    ]) == 0
    assert main([
        "--home", str(home), "log", "health",
        "--sleep", "8.5", "--gym", "no", "--energy", "5", "--date", "2026-11-19",
    ]) == 0
    n = week_numbers(home, "2026-W47")
    assert n["hours_by_area"] == {"german": 1.5, "study": 2.5}
    assert n["total_hours"] == 4.0
    assert n["health"] == {"days": 2, "sleep_avg": 8.0, "gym_days": 1, "energy_avg": 4.5}
    md = render_markdown(n)
    assert "- Logged hours: 4.0 h (german 1.5 h, study 2.5 h)" in md
    assert "- Health (2 d): sleep avg 8.0 h, gym 1 d, energy avg 4.5/5" in md


def test_week_draft_and_redteam_pack(home, capsys):
    assert main(["--home", str(home), "week", "--week", "2026-W47", "--redteam"]) == 0
    rt = capsys.readouterr().out
    assert "# Red-Team Pack · 2026-W47" in rt
    assert "Weakest point" in rt
    assert "Proofs: 3 (career 2, german 1)" in rt

    assert main(["--home", str(home), "week", "--week", "2026-W47", "--draft"]) == 0
    rel = capsys.readouterr().out.strip().replace("\\", "/")
    assert rel == "reviews/2026-W47.md"
    draft_text = (home / "reviews" / "2026-W47.md").read_text(encoding="utf-8")
    assert "# Weekly review · 2026-W47" in draft_text
    assert "proofs 3 (career 2, german 1)" in draft_text
    assert "Brake check:" in draft_text

    # Refuses to overwrite an existing weekly review file
    assert main(["--home", str(home), "week", "--week", "2026-W47", "--draft"]) == 2
    assert "already exists" in capsys.readouterr().err
