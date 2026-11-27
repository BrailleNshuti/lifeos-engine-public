"""Layering and API-hygiene tests: the module graph may only point downwards, and the number of
cross-module uses of private (underscore) names may only shrink. Made-up data: none needed."""
import ast
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "lifeos"

# A module may import only from a lower layer (a smaller number). Same layer = no import.
LAYER = {
    "diag": -2, "store": -1,
    "home": 0, "hooks": 0, "verify": 0, "guard": 0, "check": 0, "tasks": 0, "week": 0, "labcard": 0, "labscore": 0, "policy": 0,
    "context": 1, "history": 1, "calibrate": 1, "savings": 1, "vocab": 1, "lab": 1, "log": 1, "runs": 1, "kaizen": 1, "bakeoff": 1, "seats": 1,
    "ask": 2, "learn": 2, "experiment": 3, "mistakes": 3, "exam": 2, "showcase": 2, "study": 2,
    "delegate": 3, "panel": 3, "governor": 2, "canary": 3, "replay": 3, "sortcsv": 3, "router": 3, "cockpit": 3,
    "numbers": 4, "debate": 4, "debatestats": 3, "digest": 4, "demo": 4, "selftest": 4, "pipeline": 1, "decision": 2, "backup": 1, "redact": 1, "release": 0, "earn": 0, "today": 4, "lint": 1, "stale": 3, "completion": 0, "console": 0, "schema": 4, "timeline": 0, "export": 2, "arch": 0, "prove": 5, "mcp": 4,
    "notes": 4, "cmds_misc": 5, "commandsdoc": 1, "sunday": 5, "egress": 2, "selfcheck": 2, "taskclose": 2, "waiting": 1, "nextup": 5, "ratewalk": 5, "cockpit_page": 0, "dashdata": 5, "cli": 6,
}

FORBIDDEN_IN_LAB = {"ask", "delegate", "mcp", "subprocess", "socket", "urllib", "http"}

# Known cross-module uses of private names (importer, owner, name). The ratchet: this set may only shrink.
# When you make a name public (or move it), delete its row here; the test then fails if a row is stale.
KNOWN_PRIVATE_USES = set()


def _modules():
    return {p.stem: ast.parse(p.read_text(encoding="utf-8")) for p in PKG.glob("*.py") if p.stem != "__init__"}


def _internal_imports(tree):
    """Yield (owner module, imported name or None) for every `from .x import y` and `from . import x`."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            if node.module:
                for alias in node.names:
                    yield node.module, alias.name
            else:
                for alias in node.names:
                    yield alias.name, None


def _attribute_uses(tree, owner_names):
    """Yield (owner, attr) for `owner._name` attribute access, e.g. ask._check."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in owner_names:
            yield node.value.id, node.attr


def test_every_module_has_a_layer():
    assert set(_modules()) == set(LAYER), "add new modules to LAYER in tests/test_layering.py"


def test_imports_only_point_down():
    problems = []
    for name, tree in _modules().items():
        for owner, _ in _internal_imports(tree):
            if owner in LAYER and LAYER[owner] >= LAYER[name]:
                problems.append(f"{name} (layer {LAYER[name]}) imports {owner} (layer {LAYER[owner]})")
    assert not problems, problems


def test_interfaces_are_not_imported_by_others():
    for name, tree in _modules().items():
        for owner, _ in _internal_imports(tree):
            if owner == "cli":
                raise AssertionError(f"{name} imports cli")
            if owner == "mcp" and name != "cli":
                raise AssertionError(f"{name} imports mcp")


def test_lab_modules_never_import_models_or_network():
    for name, tree in _modules().items():
        if not name.startswith("lab"):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    assert root not in FORBIDDEN_IN_LAB, f"{name} imports forbidden module {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root = node.module.split(".")[0]
                    assert root not in FORBIDDEN_IN_LAB, f"{name} imports forbidden module {node.module}"
                for alias in node.names:
                    assert alias.name not in FORBIDDEN_IN_LAB, f"{name} imports forbidden name {alias.name}"



def test_private_cross_module_uses_only_shrink():
    found = set()
    for name, tree in _modules().items():
        for owner, imported in _internal_imports(tree):
            if imported and imported.startswith("_") and not imported.startswith("__"):
                found.add((name, owner, imported))
        for owner, attr in _attribute_uses(tree, set(LAYER) - {name}):
            if attr.startswith("_") and not attr.startswith("__"):
                found.add((name, owner, attr))
    assert not (found - KNOWN_PRIVATE_USES), f"new private cross-module use: {sorted(found - KNOWN_PRIVATE_USES)}"
    assert not (KNOWN_PRIVATE_USES - found), f"fixed: delete from KNOWN_PRIVATE_USES: {sorted(KNOWN_PRIVATE_USES - found)}"

