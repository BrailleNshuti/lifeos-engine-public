"""Every shipped module is imported by a test, so import-time breakage cannot hide behind CLI indirection."""
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_every_module_is_imported_by_a_test():
    modules = {p.stem for p in (ROOT / "lifeos").glob("*.py")} - {"__init__", "__main__"}
    imported = set()
    for path in (ROOT / "tests").glob("test_*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[1] for a in node.names if a.name.startswith("lifeos."))
            elif isinstance(node, ast.ImportFrom) and node.module == "lifeos":
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and str(node.module).startswith("lifeos."):
                imported.add(node.module.split(".")[1])
    assert modules <= imported, f"modules with no direct test import: {', '.join(sorted(modules - imported))}"
