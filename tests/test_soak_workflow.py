"""The scheduled soak workflow: weekly and on demand, read-only, Windows, uses scripts/soak.py, reports the counts."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT = (ROOT / ".github" / "workflows" / "soak.yml").read_text(encoding="utf-8")


def test_it_runs_weekly_and_on_demand():
    assert "schedule:" in TEXT and "cron:" in TEXT and "workflow_dispatch:" in TEXT


def test_it_runs_on_windows_where_the_write_failure_was_seen():
    assert "windows-latest" in TEXT


def test_it_uses_the_soak_script_and_reports_the_counts():
    assert "scripts/soak.py" in TEXT and "GITHUB_STEP_SUMMARY" in TEXT


def test_it_can_only_read_the_repository():
    import re
    assert "contents: read" in TEXT
    assert not re.search(r"^\s*[a-z-]+:\s*write", TEXT, re.M), "no permission may be write"


def test_it_uses_no_secrets_and_no_third_party_actions_beyond_the_official_ones():
    assert "secrets." not in TEXT
    uses = [line.split("uses:", 1)[1].strip() for line in TEXT.splitlines() if "uses:" in line]
    assert uses and all(u.startswith("actions/") for u in uses), uses


def test_it_has_a_time_limit():
    assert "timeout-minutes:" in TEXT
