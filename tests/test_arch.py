from pathlib import Path

from lifeos import arch
from lifeos.cli import main

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "docs" / "ARCHITECTURE-GRAPH.md"


def test_graph_lists_every_module_with_a_depth():
    g = arch.graph()
    assert g["verify"]["depth"] == 0 and g["cli"]["depth"] == max(v["depth"] for v in g.values())
    assert "ask" in g["delegate"]["imports"] and "cli" not in {i for v in g.values() for i in v["imports"]}


def test_depth_is_one_more_than_the_deepest_import():
    for name, v in arch.graph().items():
        assert v["depth"] == (1 + max(arch.graph()[i]["depth"] for i in v["imports"]) if v["imports"] else 0), name


def test_mermaid_has_every_module_and_every_edge():
    text = arch.mermaid(arch.graph())
    assert text.startswith("graph BT") and text.count("-->") == sum(len(v["imports"]) for v in arch.graph().values())
    assert all(f"  {n}[" in text or f"{n}[" in text for n in arch.graph())


def test_checked_in_graph_is_not_stale():
    assert FILE.exists(), "run: lifeos arch --write docs/ARCHITECTURE-GRAPH.md"
    assert FILE.read_text(encoding="utf-8") == arch.page(), "docs are stale: lifeos arch --write docs/ARCHITECTURE-GRAPH.md"


def test_cli_write_and_check(tmp_path, capsys):
    out = tmp_path / "g.md"
    assert main(["arch", "--check", str(out)]) == 1  # missing file counts as stale
    assert main(["arch", "--write", str(out)]) == 0
    assert main(["arch", "--check", str(out)]) == 0
    out.write_text("old")
    assert main(["arch", "--check", str(out)]) == 1
