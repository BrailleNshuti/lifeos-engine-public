"""Find and read the LifeOS data repo (the private 'home')."""
import os
from pathlib import Path

CORE_FILES = ("rules.md", "me.md", "now.md")


class HomeError(Exception):
    pass


def find_home(explicit=None):
    """Return the data repo path from --home, LIFEOS_HOME or the current folder."""
    path = Path(explicit or os.environ.get("LIFEOS_HOME", ".")).expanduser().resolve()
    if not (path / "now.md").exists():
        raise HomeError(f"No LifeOS data repo at {path} (now.md is missing). Set LIFEOS_HOME or pass --home.")
    return path


def estimate_tokens(text):
    """Rough token estimate: about four characters per token for English text."""
    return (len(text) + 3) // 4


def default_example():
    """The made-up demo home: the repository's `examples/demo-home` when it is there (a checkout), else the copy bundled in the
    package (`lifeos/_demo_home`, kept identical by a test), so `lifeos demo` also works after a plain `pip install`."""
    checkout = Path(__file__).resolve().parent.parent / "examples" / "demo-home"
    return checkout if checkout.is_dir() else Path(__file__).resolve().parent / "_demo_home"
