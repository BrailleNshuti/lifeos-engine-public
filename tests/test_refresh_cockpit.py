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
    assert len(list(out.glob("*.json"))) == 7
    for dataset in ("numbers", "runs", "ratings", "tasks", "waiting", "egress", "latency"):
        assert f"dataset '{dataset}'" in text
    assert "private" in text


def test_the_default_folder_is_next_to_the_home_not_inside_it(home, capsys):
    assert refresh.main(["--home", str(home)]) == 0
    assert (home.parent / "lifeos-cockpit-export" / "numbers.json").exists()
    assert not (home / "lifeos-cockpit-export").exists()


def test_a_folder_inside_the_repo_is_refused(home, capsys):
    assert refresh.main(["--home", str(home), "--out", str(ROOT / "docs" / "export")]) == 2
    assert not (ROOT / "docs" / "export").exists()
