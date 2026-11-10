from lifeos.context import build_pack


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
