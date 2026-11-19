import pytest

from lifeos import release
from lifeos.cli import main

LOG = """# Changelog

## [Unreleased]

- `lifeos a`: new thing.
- Fixed a crash in `b`.

## [0.3.0] - 2026-11-18

- old
"""


def make(tmp_path, version="0.3.0", changelog=LOG, init=None):
    (tmp_path / "lifeos").mkdir()
    (tmp_path / "pyproject.toml").write_text(f'[project]\nversion = "{version}"\n', encoding="utf-8")
    (tmp_path / "lifeos" / "__init__.py").write_text(f'__version__ = "{init or version}"\n', encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    return tmp_path


def test_a_new_command_proposes_a_minor_bump(tmp_path):
    plan = release.plan(make(tmp_path))
    assert plan["current"] == "0.3.0" and plan["proposed"] == "0.4.0" and plan["entries"] == 2
    assert "## [0.4.0]" in plan["notes"] and "`lifeos a`" in plan["notes"]


def test_only_fixes_propose_a_patch_bump(tmp_path):
    plan = release.plan(make(tmp_path, changelog=LOG.replace("- `lifeos a`: new thing.\n", "")))
    assert plan["proposed"] == "0.3.1"


def bump(tmp_path, *entries):
    log = "# Changelog\n\n## [Unreleased]\n\n" + "\n".join(entries) + "\n\n## [0.3.0] - 2026-11-18\n\n- old\n"
    return release.plan(make(tmp_path, changelog=log))["proposed"]


def test_the_word_new_inside_a_fix_does_not_make_a_feature(tmp_path):
    # the real 0.4.1 entries: "New tests render ..." once made the tool propose 0.5.0
    assert bump(tmp_path,
                "- Fix: `lifeos --help` crashed because of a bare `%`. New tests render every help text.",
                '- Docs: the README command table is headed "What it does".') == "0.3.1"


@pytest.mark.parametrize("entry", [
    "- Fixed the renewed token handling in `b`.",
    "- Fix: `lifeos lint` crashed on a task without a due date.",
    "- Tests: new property tests for the guard.",
    "- Docs: a new example in the README.",
    "- Robustness: a knewline in a log no longer crashes `lifeos runs`.",
])
def test_fixes_docs_and_tests_stay_patch(tmp_path, entry):
    assert bump(tmp_path, entry) == "0.3.1"


@pytest.mark.parametrize("entry", [
    "- `lifeos debate`: blind multi-model debate.",
    "- A new command that lists stale tasks.",
    "- Adds a new flag `--json` to `lifeos runs`.",
])
def test_a_command_or_a_new_feature_proposes_a_minor_bump(tmp_path, entry):
    assert bump(tmp_path, entry) == "0.4.0"


def test_one_feature_among_fixes_is_enough_for_a_minor_bump(tmp_path):
    assert bump(tmp_path, "- Fix: a typo.", "- `lifeos debate`: blind debate.", "- Docs: more.") == "0.4.0"


def test_version_mismatch_is_a_problem(tmp_path):
    assert any("differ" in p for p in release.plan(make(tmp_path, init="0.2.9"))["problems"])


def test_nothing_unreleased_is_a_problem(tmp_path):
    empty = LOG.replace("- `lifeos a`: new thing.\n- Fixed a crash in `b`.\n", "")
    plan = release.plan(make(tmp_path, changelog=empty))
    assert plan["entries"] == 0 and any("nothing" in p.lower() for p in plan["problems"])


def test_cli_prints_a_plan_and_never_tags(tmp_path, capsys):
    root = make(tmp_path)
    assert main(["release", "--repo", str(root)]) == 0
    out = capsys.readouterr().out
    assert "0.4.0" in out and "You decide" in out
