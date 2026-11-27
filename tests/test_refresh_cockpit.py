"""scripts/refresh_cockpit.py runs the export and says which file feeds which dataset (round 4 item 25)."""
import importlib.util
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("refresh_cockpit", ROOT / "scripts" / "refresh_cockpit.py")
refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def test_it_exports_seven_files_and_names_the_datasets(home, tmp_path, capsys):
    out = tmp_path / "export"
    assert refresh.main(["--home", str(home), "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert len(list(out.glob("*.json"))) >= 8  # seven exported files plus seats.json (and shipped.json when `gh` works)
    for dataset in ("numbers", "runs", "ratings", "tasks", "waiting", "egress", "latency", "seats"):
        assert f"dataset '{dataset}'" in text
    assert "private" in text


def test_the_default_folder_is_next_to_the_home_not_inside_it(home, capsys):
    assert refresh.main(["--home", str(home)]) == 0
    assert (home.parent / "lifeos-cockpit-export" / "numbers.json").exists()
    assert not (home / "lifeos-cockpit-export").exists()


def test_a_folder_inside_the_repo_is_refused(home, capsys):
    assert refresh.main(["--home", str(home), "--out", str(ROOT / "docs" / "export")]) == 2
    assert not (ROOT / "docs" / "export").exists()


def test_the_seat_table_matches_the_engines_blocked_jobs():
    from lifeos import seats
    assert set(seats.BLOCKS) == set(seats.CANNOT), "a seat in CANNOT needs a row in BLOCKS and the other way round"
    rows = {r["seat"]: r for r in seats.capability_rows()}
    assert set(rows) == {"claude", "codex", "gemini", "grok", "qwen", "ollama"}
    assert rows["grok"]["shop"] == rows["grok"]["files"] == rows["grok"]["shell"] == "blocked" and rows["grok"]["web"] == "ok"
    assert rows["qwen"]["web"] == rows["ollama"]["web"] == "blocked" and rows["claude"]["web"] == "ok"
    assert [r["kind"] for r in rows.values()].count("local") == 2


def test_shipped_rows_come_from_merged_pull_request_titles():
    listing = [{"number": 12, "title": "fix: two ask processes no longer collide"}, {"number": 5, "title": "feat: lifeos next"},
               {"number": 9, "title": "A title with no prefix"}, {"number": 7, "title": "test: canary proof"}]
    rows = refresh.shipped_rows(listing)
    assert [r["pr"] for r in rows] == [5, 7, 9, 12]
    assert rows[0] == {"pr": 5, "area": "command", "what": "lifeos next"}
    assert rows[1]["area"] == "safety" and rows[2]["area"] == "docs" and rows[3]["area"] == "data"


def test_the_export_writes_seats_and_survives_a_missing_gh(home, tmp_path, monkeypatch):
    out = tmp_path / "export"

    def no_gh(*a, **k):
        raise FileNotFoundError("gh")
    written = refresh.write_extra(out_dir := (out.mkdir() or out), run=no_gh)
    assert [p.name for p in written] == ["seats.json"] and (out_dir / "seats.json").exists()
    assert not (out_dir / "shipped.json").exists()


def test_the_export_writes_shipped_when_gh_answers(tmp_path):
    import json

    class Done:
        returncode, stdout = 0, json.dumps([{"number": 3, "title": "docs: a page"}])
    written = refresh.write_extra(tmp_path, run=lambda *a, **k: Done())
    assert sorted(p.name for p in written) == ["seats.json", "shipped.json"]
