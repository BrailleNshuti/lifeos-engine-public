"""Eight threads start together on a CSV log that does not exist yet: each of the four writers must create the file once and
lose no row (found in CI 2026-11-27: one row of 50 missing when two processes created the file at the same moment)."""
import csv
import shutil
import threading

import pytest

from lifeos import calibrate, experiment, learn, vocab

THREADS, PER = 8, 15


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    for name in ("ratings.csv", "predictions.csv", "experiments.csv", "vocab.csv"):
        (target / "logs" / name).unlink(missing_ok=True)
    return target


def race(work):
    start = threading.Barrier(THREADS)
    errors = []

    def run(index):
        try:
            start.wait()
            for i in range(PER):
                work(index, i)
        except Exception as err:  # noqa: BLE001 - the test reports every failure
            errors.append(repr(err))

    threads = [threading.Thread(target=run, args=(n,)) for n in range(THREADS)]
    [t.start() for t in threads]
    [t.join(timeout=120) for t in threads]
    return errors


def rows(home, name):
    return list(csv.DictReader(open(home / "logs" / name, encoding="utf-8")))


def test_ratings(home):
    errors = race(lambda n, i: learn.add_rating(home, "T-261116", "claude", 3, "implement a python module", note=f"{n}-{i}"))
    assert not errors, errors[:2]
    assert len(rows(home, "ratings.csv")) == THREADS * PER


def test_predictions(home):
    errors = race(lambda n, i: calibrate.predict(home, f"claim {n}-{i}", 60))
    assert not errors, errors[:2]
    assert len(rows(home, "predictions.csv")) == THREADS * PER


def test_vocabulary(home):
    errors = race(lambda n, i: vocab.add(home, f"Wort{n}-{i}", "word"))
    assert not errors, errors[:2]
    assert len(rows(home, "vocab.csv")) == THREADS * PER


def test_the_header_is_written_exactly_once(home):
    race(lambda n, i: learn.add_rating(home, "T-261116", "claude", 3, "implement a python module", note=f"{n}-{i}"))
    text = (home / "logs" / "ratings.csv").read_text(encoding="utf-8")
    assert text.count("date,task,model,score,kind,note") == 1
