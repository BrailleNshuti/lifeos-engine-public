"""Four processes at once on one home: one rates, one closes tasks, one adds waiting items, one only reads (today, selfcheck).
Nobody crashes, nothing is lost, and the files are sound at the end (round 5 item 2). Made-up data only."""
import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
N = 12
TASK = "---\nid: {id}\ngoal: a made-up goal\ndone_when: a checkable finish line\nroute: claude\nlevel: L0\nstatus: doing\ndue: \n---\n## Result (written back here)\n\n## Proof\n"
HEAD = "import sys\nsys.path.insert(0, sys.argv[2])\nhome = sys.argv[1]\n"
CODES = {
    "rate": HEAD + "from lifeos import learn\nfor i in range(%d):\n    learn.add_rating(home, 'T-261201-t%%02d' %% (i %% %d), 'claude', 3, 'implement a python module', note='n%%d' %% i)\n" % (N * 2, N),
    "close": HEAD + "from lifeos import taskclose\nfor i in range(%d):\n    taskclose.close(home, 'T-261201-t%%02d' %% i, 'tests/test_x.py')\n" % N,
    "wait": HEAD + "from lifeos import waiting\nfor i in range(%d):\n    waiting.add(home, 'item %%d' %% i)\n" % (N * 2),
    "read": HEAD + "import datetime as dt\nfrom lifeos import selfcheck, today\nfor i in range(%d):\n    today.build(home, dt.date(2026, 12, 1))\n    selfcheck.run(home)\n" % (N * 2),
}


@pytest.fixture
def home(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "now.md").write_text("# now", encoding="utf-8")
    for i in range(N):
        tid = f"T-261201-t{i:02d}"
        (tmp_path / "tasks" / f"{tid}.md").write_text(TASK.format(id=tid), encoding="utf-8")
    return tmp_path


def test_four_kinds_of_process_at_once_lose_nothing_and_never_crash(home):
    procs = {name: subprocess.Popen([sys.executable, "-c", code, str(home), str(ROOT)], stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True) for name, code in CODES.items()}
    results = {name: p.communicate(timeout=240) + (p.returncode,) for name, p in procs.items()}
    for name, (out, err, code) in results.items():
        assert code == 0, f"{name} failed: {err[-1800:]}"
    rows = list(csv.DictReader(open(home / "logs" / "ratings.csv", encoding="utf-8", newline="")))
    assert len(rows) == N * 2
    assert len(json.loads((home / "waiting.json").read_text(encoding="utf-8"))) == N * 2
    for i in range(N):
        assert "status: done" in (home / "tasks" / f"T-261201-t{i:02d}.md").read_text(encoding="utf-8")
    from lifeos import selfcheck
    assert selfcheck.exit_code(selfcheck.run(home)) == 0
