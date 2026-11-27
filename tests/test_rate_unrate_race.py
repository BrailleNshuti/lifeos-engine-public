"""`rate` and `unrate` racing on the same ratings file: no added row is lost, no removed row comes back, no crash.
(round 4 item 5.) Made-up data only."""
import csv
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ADDER = """
import sys
sys.path.insert(0, sys.argv[3])
from lifeos import learn
home, count = sys.argv[1], int(sys.argv[2])
for i in range(count):
    learn.add_rating(home, "T-261201-add", "claude", 3, "implement a python module", note=f"add-{i}")
"""
REMOVER = """
import sys
sys.path.insert(0, sys.argv[3])
from lifeos import learn
home, count = sys.argv[1], int(sys.argv[2])
for i in range(count):
    assert learn.remove_last(home, "T-261201-old") is not None
"""
N = 20


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def test_adding_and_removing_at_once_keeps_every_row_that_should_stay(home):
    from lifeos import learn
    for i in range(N):
        learn.add_rating(home, "T-261201-old", "codex", 2, "implement a python module", note=f"old-{i}")
    keep_before = [r for r in learn.read_ratings(home) if r["task"] != "T-261201-old"]
    procs = [subprocess.Popen([sys.executable, "-c", code, str(home), str(N), str(ROOT)], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True) for code in (ADDER, REMOVER)]
    for p in procs:
        out, err = p.communicate(timeout=180)
        assert p.returncode == 0, err[-400:]
    rows = list(csv.DictReader(open(home / "logs" / "ratings.csv", encoding="utf-8")))
    assert [r["note"] for r in rows if r["task"] == "T-261201-add"].count("") == 0
    assert {r["note"] for r in rows if r["task"] == "T-261201-add"} == {f"add-{i}" for i in range(N)}
    assert not [r for r in rows if r["task"] == "T-261201-old"]
    assert len([r for r in rows if r["task"] not in ("T-261201-add", "T-261201-old")]) == len(keep_before)
