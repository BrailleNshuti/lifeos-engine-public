from lifeos import lint
from lifeos.cli import main

GOOD = """---
id: T-261101-ok
goal: Ship it
done_when: tests green and the pull request merged
route: Claude Code -> Codex review
level: L2
status: doing
due: 2026-11-22
---
## Proof
"""


def put(home, name, text):
    (home / "tasks").mkdir(exist_ok=True)
    (home / "tasks" / f"{name}.md").write_text(text, encoding="utf-8")


def problems(home):
    return {(p["task"], p["problem"].split(":")[0]) for p in lint.check(home)}


def test_a_good_task_has_no_problems(tmp_path):
    put(tmp_path, "T-261101-ok", GOOD)
    assert lint.check(tmp_path) == []


def test_missing_and_placeholder_fields_are_named(tmp_path):
    put(tmp_path, "T-261101-ok", GOOD.replace("done_when: tests green and the pull request merged", "done_when: TODO (you write this line)"))
    put(tmp_path, "T-261102-x", GOOD.replace("id: T-261101-ok", "id: T-999999-other").replace("goal: Ship it\n", ""))
    got = problems(tmp_path)
    assert ("T-261101-ok", "done_when") in got
    assert ("T-261102-x", "goal") in got and ("T-261102-x", "id") in got


def test_bad_values_are_caught(tmp_path):
    put(tmp_path, "T-261101-ok", GOOD.replace("level: L2", "level: L9").replace("status: doing", "status: maybe").replace("2026-11-22", "next week"))
    got = problems(tmp_path)
    assert {("T-261101-ok", "level"), ("T-261101-ok", "status"), ("T-261101-ok", "due")} <= got


def test_done_without_proof_is_flagged_rule_1(tmp_path):
    put(tmp_path, "T-261101-ok", GOOD.replace("status: doing", "status: done").replace("## Proof\n", "## Proof\n\n## Ledger\n"))
    assert ("T-261101-ok", "proof") in problems(tmp_path)
    put(tmp_path, "T-261103-fine", GOOD.replace("T-261101-ok", "T-261103-fine").replace("status: doing", "status: done") + "https://example.org/pr/1\n")
    assert not any(p[0] == "T-261103-fine" for p in problems(tmp_path))


def test_no_frontmatter_and_cli_exit_codes(tmp_path, capsys):
    (tmp_path / "now.md").write_text("# now\n", encoding="utf-8")
    put(tmp_path, "T-261101-bare", "just text\n")
    assert main(["--home", str(tmp_path), "lint"]) == 1
    assert "frontmatter" in capsys.readouterr().out
    (tmp_path / "tasks" / "T-261101-bare.md").unlink()
    put(tmp_path, "T-261101-ok", GOOD)
    assert main(["--home", str(tmp_path), "lint"]) == 0
