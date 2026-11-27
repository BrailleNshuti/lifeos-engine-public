"""`lifeos route` says what your own ratings suggest, as advice only (round 4 item 11). Made-up data only."""
import json
import shutil

import pytest

from lifeos import learn
from lifeos.cli import main


@pytest.fixture
def home(tmp_path, demo, monkeypatch):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    monkeypatch.setenv("LIFEOS_HOME", str(target))
    return target


def test_route_prints_the_learned_line_without_evidence(home, capsys):
    main(["route", "implement a python module"])
    assert "learned: fewer than" in capsys.readouterr().out


def test_route_names_a_better_seat_once_the_evidence_is_clear(home, capsys):
    text = "implement a python module"
    for model, score in (("claude", 2), ("claude", 2), ("claude", 2), ("codex", 5), ("codex", 5), ("codex", 5)):
        learn.add_rating(home, "T-261116", model, score, text)
    main(["route", text])
    out = capsys.readouterr().out
    assert "learned: codex averages" in out


def test_json_output_stays_pure_json(home, capsys):
    main(["route", "--json", "implement a python module"])
    json.loads(capsys.readouterr().out)
