"""Two processes adding rows to the same CSV log at once must not lose a row or crash.

Found 2026-11-27 by racing two `learn.add_rating` loops: only 40 of 80 rows survived and one process died with a
PermissionError (the same winerror 5 as the unexplained Windows write failure). The read-modify-write of `append_csv_row`
was not under the store lock."""
import csv
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHILD = """
import sys
sys.path.insert(0, sys.argv[4])
from lifeos import learn
home, tag, count = sys.argv[1], sys.argv[2], int(sys.argv[3])
for i in range(count):
    learn.add_rating(home, "T-261116", "claude", 3, "implement a python module", note=f"{tag}-{i}")
"""
PER_PROCESS = 25


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def test_two_processes_adding_ratings_lose_nothing(home):
    procs = [subprocess.Popen([sys.executable, "-c", CHILD, str(home), tag, str(PER_PROCESS), str(ROOT)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for tag in ("a", "b")]
    results = [p.communicate(timeout=180) + (p.returncode,) for p in procs]
    for out, err, code in results:
        assert code == 0, err[-400:]
    rows = list(csv.DictReader(open(home / "logs" / "ratings.csv", encoding="utf-8")))
    notes = {r["note"] for r in rows}
    assert len(rows) == 2 * PER_PROCESS, len(rows)
    assert notes == {f"{t}-{i}" for t in ("a", "b") for i in range(PER_PROCESS)}
