"""The example pipelines in the demo home must load, dry-run and (they are read-only) run clean."""
import shutil
from pathlib import Path

import pytest

from lifeos import pipeline
from lifeos.cli import main

NAMES = sorted(p.stem for p in (Path(__file__).resolve().parent.parent / "examples" / "demo-home" / "pipelines").glob("*.json"))


def test_there_are_examples():
    assert {"morning", "sunday", "before-push"} <= set(NAMES)


@pytest.mark.parametrize("name", NAMES)
def test_each_example_runs_clean_on_a_copy_of_the_demo_home(name, tmp_path, demo, capsys):
    home = tmp_path / "home"
    shutil.copytree(demo, home)
    assert [r["status"] for r in pipeline.run(home, name, main, execute=False)] == ["planned"] * len(pipeline.load(home, name))
    capsys.readouterr()
    assert main(["--home", str(home), "pipeline", name, "--run"]) == 0
    assert "failed" not in capsys.readouterr().out
