"""`lifeos demo` and `selftest` must work after a plain `pip install`, so the made-up demo home is bundled in the package
(round 7). The bundled copy must stay identical to `examples/demo-home`."""
import hashlib
import shutil
from pathlib import Path

from lifeos import home as homemod

ROOT = Path(__file__).resolve().parents[1]
SOURCE, BUNDLED = ROOT / "examples" / "demo-home", ROOT / "lifeos" / "_demo_home"


def files(base):
    return {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(base.rglob("*"))
            if p.is_file() and p.name != ".store.lock"}


def test_the_bundled_copy_is_identical_to_the_example():
    assert files(BUNDLED) == files(SOURCE), "copy examples/demo-home into lifeos/_demo_home (without logs/.store.lock)"


def test_the_demo_runs_from_the_bundled_copy(tmp_path, capsys):
    from lifeos.cli import main
    copy = tmp_path / "demo-home"
    shutil.copytree(BUNDLED, copy)
    assert main(["demo", "--example", str(copy)]) == 0
    assert "All five held" in capsys.readouterr().out


def test_the_default_falls_back_to_the_bundle_when_there_is_no_checkout(monkeypatch):
    real = Path.is_dir
    monkeypatch.setattr(Path, "is_dir", lambda self: False if self.name == "demo-home" and "examples" in self.parts else real(self))
    assert homemod.default_example() == BUNDLED


def test_the_package_data_lists_the_bundle():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "_demo_home" in text and "package-data" in text
