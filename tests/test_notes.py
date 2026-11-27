from lifeos import notes


TASK = """---
id: T-1
goal: Find the current shop price
done_when: price and source URL
route: Grok
level: L1
status: doing
---
## Context (links, not essays)

## Task
Find the current shop price and availability.
"""


def test_pre_notes_warns_grok_about_shop_tasks(tmp_path):
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    (tasks / "T-1.md").write_text(TASK, encoding="utf-8")

    found = notes.pre_notes(tmp_path, "grok", "T-1")

    assert len(found) == 1
    assert "shop" in found[0] and "block" in found[0]


def test_post_notes_reports_a_bad_answer(tmp_path):
    task = tmp_path / "T-1.md"
    task.write_text(
        TASK + "\n## Result · grok · 2026-11-27\nI'll save the price and source.\n",
        encoding="utf-8",
    )

    found = notes.post_notes(task)

    assert len(found) == 1
    assert found[0].startswith("CHECK (free, no model): ")
    assert "promises to save" in found[0]


def test_pre_notes_returns_empty_for_a_missing_task(tmp_path):
    assert notes.pre_notes(tmp_path, "grok", "T-missing") == []


def test_post_notes_returns_empty_for_a_missing_task(tmp_path):
    assert notes.post_notes(tmp_path / "T-missing.md") == []
