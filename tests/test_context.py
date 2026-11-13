from lifeos.context import build_pack, build_review_pack, explain_pack, pack_hash, render_explanation
import pytest



def test_pack_order_and_budget(demo):
    pack, tokens = build_pack(demo, "T-261116", budget=6000)
    assert pack.index("=== rules.md") < pack.index("=== tasks/") < pack.index("=== now.md") < pack.index("=== me.md")
    assert tokens <= 6000


def test_pack_drops_lower_priority_files_first(demo):
    pack, tokens = build_pack(demo, None, budget=150)
    assert "=== rules.md" in pack and "now.md" not in pack and tokens <= 150


def test_pack_always_keeps_a_trimmed_rules_file(demo):
    pack, tokens = build_pack(demo, None, budget=60)
    assert "rules.md (trimmed to fit 60 tokens)" in pack and tokens <= 80


@pytest.mark.parametrize("budget", [0, -1, 50001, "6000", True])
def test_invalid_budgets_are_refused(demo, budget):
    with pytest.raises(ValueError, match="1 to 50000"):
        build_pack(demo, budget=budget)


def test_explain_pack_reports_included_trimmed_and_excluded_files(demo):
    info = explain_pack(demo, "T-261116", budget=250, task_first=True, names=("TASK", "rules.md"))
    statuses = {item["name"]: item["status"] for item in info["items"]}
    assert statuses["tasks/T-261116-demo-cli.md"] == "included"
    assert statuses["now.md"] == "excluded (minimal mode)"
    assert len(info["sha256"]) == 12
    rendered = render_explanation(info)
    assert "sha256" in rendered and "excluded (minimal mode)" in rendered


def test_build_review_pack_strips_existing_results_for_blind_review(demo, tmp_path):
    import shutil

    home = tmp_path / "home"
    shutil.copytree(demo, home)
    task = home / "tasks" / "T-261116-demo-cli.md"
    task.write_text(task.read_text(encoding="utf-8") + "\n## Result · claude · 2026-11-20\nSECRET FIRST ANSWER\n", encoding="utf-8")
    pack, _ = build_review_pack(home, "T-261116", diff_text="diff --git a/x.py b/x.py")
    assert "SECRET FIRST ANSWER" not in pack
    assert "=== diff ===" in pack
    assert len(pack_hash(pack)) == 12


