"""Seeded property tests (round 4 item 30): random inputs from a printed seed, so a failure can be replayed.

Replay one failure with: LIFEOS_SEED=<number> pytest tests/test_seeded_properties.py
Standard library only (`random`). The default seeds are fixed, so CI stays deterministic."""
import csv
import datetime as dt
import json
import os
import random
import string

import pytest

from lifeos import egress, store, sunday, today, week
from lifeos.context import task_file

SEEDS = [int(os.environ["LIFEOS_SEED"])] if os.environ.get("LIFEOS_SEED") else [1, 2, 3, 4, 5, 6, 7, 8]
ALPHABET = string.ascii_letters + string.digits + " ,;:\"'\n\t.-_/|äöüß€漢字🙂"


def word(rng, longest=40):
    return "".join(rng.choice(ALPHABET) for _ in range(rng.randint(0, longest)))


def clean(value):
    """What a CSV log keeps of a value: a lone NUL or carriage return is not stored, the rest comes back as written."""
    return value.replace("\0", "").replace("\r", "")


@pytest.mark.parametrize("seed", SEEDS)
def test_csv_rows_round_trip_whatever_the_text(tmp_path, seed):
    rng = random.Random(seed)
    path = tmp_path / "logs" / "log.csv"
    header = ["date", "task", "note"]
    rows = [[f"2026-11-{rng.randint(1, 28):02d}", f"T-{rng.randint(100000, 999999)}", word(rng)] for _ in range(25)]
    for row in rows:
        store.append_csv_row_creating(path, header, row)
    with path.open(encoding="utf-8", newline="") as fh:
        back = list(csv.reader(fh))
    assert back[0] == header, f"seed {seed}"
    assert len(back) == len(rows) + 1, f"seed {seed}"
    for want, got in zip(rows, back[1:]):
        assert [clean(v) for v in want] == got, f"seed {seed}"
    parsed = store.read_csv_rows(path)
    assert len(parsed) == len(rows), f"seed {seed}"


@pytest.mark.parametrize("seed", SEEDS)
def test_task_ids_resolve_by_unique_prefix_and_never_by_junk(tmp_path, seed):
    rng = random.Random(seed)
    (tmp_path / "tasks").mkdir()
    stems = sorted({f"T-26{rng.randint(1000, 1299)}-{''.join(rng.choice('abcdefgh') for _ in range(rng.randint(3, 9)))}" for _ in range(20)})
    for stem in stems:
        (tmp_path / "tasks" / f"{stem}.md").write_text("x", encoding="utf-8")
    for stem in stems:
        assert task_file(tmp_path, stem).stem == stem, f"seed {seed}"
        cut = stem[: rng.randint(3, len(stem))]
        hits = [s for s in stems if s.startswith(cut)]
        if len(hits) == 1:
            assert task_file(tmp_path, cut).stem == stem, f"seed {seed} {cut}"
        else:
            with pytest.raises(ValueError):
                task_file(tmp_path, cut)
    for junk in ("", "x", "T-", "../T-261116", "T-26/../x", "T-a b", "t-261116"):
        with pytest.raises((ValueError, FileNotFoundError)):
            task_file(tmp_path, junk)


@pytest.mark.parametrize("seed", SEEDS)
def test_the_thirty_day_window_includes_exactly_the_days_inside_it(tmp_path, seed):
    rng = random.Random(seed)
    today = dt.date(2026, 11, 27) + dt.timedelta(days=rng.randint(-200, 200))
    (tmp_path / "logs").mkdir()
    records, expect = [], 0
    for _ in range(60):
        offset = rng.randint(-5, 45)
        day = today - dt.timedelta(days=offset)
        inside = 0 <= offset < 30
        expect += inside
        records.append({"command": "ask", "model": "claude", "status": "ok", "tokens": 1, "date": day.isoformat()})
    (tmp_path / "logs" / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    rows = egress.report(tmp_path, today=today, days=30)
    got = rows[0]["calls"] if rows else 0
    assert got == expect, f"seed {seed}: expected {expect} calls in the window, got {got}"


@pytest.mark.parametrize("seed", SEEDS)
def test_days_left_matches_date_distance(seed):
    rng = random.Random(seed)
    base = dt.date(2024, 1, 1) + dt.timedelta(days=rng.randint(0, 1_500))
    for _ in range(50):
        gap = rng.randint(-800, 800)
        expected = {0: "today", 1: "tomorrow"}.get(gap, f"in {gap} days" if gap > 0 else f"{-gap} days late")
        assert today.days_left(base + dt.timedelta(days=gap), base) == expected, f"seed {seed}, gap {gap}"


@pytest.mark.parametrize("seed", SEEDS)
def test_sunday_file_uses_the_dates_iso_week(tmp_path, seed):
    rng = random.Random(seed)
    for _ in range(50):
        day = dt.date(2020, 1, 1) + dt.timedelta(days=rng.randint(0, 3_650))
        iso = day.isocalendar()
        assert sunday.week_file(tmp_path, day).name == f"week-{iso.year}-W{iso.week:02d}.md", f"seed {seed}, day {day}"


@pytest.mark.parametrize("seed", SEEDS)
def test_week_bounds_round_trip_across_new_year(seed):
    rng = random.Random(seed)
    for year in range(2020, 2031):
        day = dt.date(year, 12, 25) + dt.timedelta(days=rng.randint(0, 13))
        iso = day.isocalendar()
        start, end = week.week_bounds(today=day)
        assert start <= day <= end and start.weekday() == 0 and end - start == dt.timedelta(days=6), f"seed {seed}, day {day}"
        assert week.week_bounds(f"{iso.year}-W{iso.week:02d}") == (start, end), f"seed {seed}, day {day}"
