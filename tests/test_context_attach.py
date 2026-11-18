import shutil

import pytest

from lifeos.context import build_pack, explain_pack


def make_home(tmp_path, demo, context_lines):
    home = tmp_path / "home"
    shutil.copytree(demo, home)
    task = next((home / "tasks").glob("T-261116*.md"))
    text = task.read_text(encoding="utf-8")
    head, rest = text.split("## Context (links, not essays)", 1)
    after = rest.split("\n## ", 1)[1]
    task.write_text(head + "## Context (links, not essays)\n" + context_lines + "\n\n## " + after, encoding="utf-8")
    (home / "system").mkdir(exist_ok=True)
    (home / "system" / "briefing.md").write_text("# Briefing\nThe engine is public.\n", encoding="utf-8")
    return home


@pytest.mark.parametrize("line", [
    "system/briefing.md",
    "- system/briefing.md",
    "* `system/briefing.md`",
    "@system/briefing.md",
    "system\\briefing.md",
])
def test_listed_file_is_attached(tmp_path, demo, line):
    home = make_home(tmp_path, demo, line)
    pack, _ = build_pack(home, "T-261116", task_first=True, names=("TASK", "rules.md"))
    assert "=== system/briefing.md (attached) ===" in pack
    assert "The engine is public." in pack
    assert pack.index("=== tasks/") < pack.index("=== system/briefing.md")


def test_plain_text_lines_are_not_attached(tmp_path, demo):
    home = make_home(tmp_path, demo, "Read the briefing please\nsystem/missing.md")
    pack, _ = build_pack(home, "T-261116", task_first=True, names=("TASK", "rules.md"))
    assert "(attached)" not in pack


@pytest.mark.parametrize("line", ["../outside.md", "/etc/passwd", "C:\\Windows\\win.ini", "system/../../outside.md"])
def test_paths_outside_home_are_never_attached(tmp_path, demo, line):
    (tmp_path / "outside.md").write_text("SECRET", encoding="utf-8")
    home = make_home(tmp_path, demo, line)
    pack, _ = build_pack(home, "T-261116", task_first=True, names=("TASK", "rules.md"))
    assert "SECRET" not in pack and "(attached)" not in pack


def test_symlink_escape_is_refused(tmp_path, demo):
    (tmp_path / "outside.md").write_text("SECRET", encoding="utf-8")
    home = make_home(tmp_path, demo, "system/link.md")
    try:
        (home / "system" / "link.md").symlink_to(tmp_path / "outside.md")
    except OSError:
        pytest.skip("symlinks not available")
    pack, _ = build_pack(home, "T-261116", task_first=True, names=("TASK", "rules.md"))
    assert "SECRET" not in pack


@pytest.mark.parametrize("name", ["data.csv", "tool.py", ".env", "key.pem", "logs/ledger.md", ".git/config.md"])
def test_only_notes_outside_logs_and_git_are_attached(tmp_path, demo, name):
    home = make_home(tmp_path, demo, name)
    target = home / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("PRIVATE-BODY", encoding="utf-8")
    pack, _ = build_pack(home, "T-261116", task_first=True, names=("TASK", "rules.md"))
    assert "PRIVATE-BODY" not in pack


def test_at_most_four_files_and_no_duplicates(tmp_path, demo):
    home = make_home(tmp_path, demo, "\n".join(["system/briefing.md"] * 2 + [f"system/n{i}.md" for i in range(6)]))
    for i in range(6):
        (home / "system" / f"n{i}.md").write_text(f"note {i}\n", encoding="utf-8")
    pack, _ = build_pack(home, "T-261116", task_first=True, names=("TASK", "rules.md"))
    assert pack.count("(attached)") == 4
    assert pack.count("=== system/briefing.md") == 1


def test_attachment_is_trimmed_by_the_budget(tmp_path, demo):
    home = make_home(tmp_path, demo, "system/briefing.md")
    (home / "system" / "briefing.md").write_text("word " * 20000, encoding="utf-8")
    pack, tokens = build_pack(home, "T-261116", budget=1500, task_first=True, names=("TASK", "rules.md"))
    assert tokens <= 1600


def test_explain_pack_lists_attachments(tmp_path, demo):
    home = make_home(tmp_path, demo, "system/briefing.md")
    info = explain_pack(home, "T-261116", task_first=True, names=("TASK", "rules.md"))
    statuses = {item["name"]: item["status"] for item in info["items"]}
    assert statuses["system/briefing.md (attached)"] == "included"
    pack, _ = build_pack(home, "T-261116", task_first=True, names=("TASK", "rules.md"))
    assert info["sha256"] == __import__("lifeos.context", fromlist=["pack_hash"]).pack_hash(pack)


def test_no_context_section_means_no_change(demo):
    pack, _ = build_pack(demo, "T-261116", task_first=True, names=("TASK", "rules.md"))
    assert "(attached)" not in pack
