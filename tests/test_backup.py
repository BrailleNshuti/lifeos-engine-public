import datetime as dt
import hashlib
import json

import pytest

from lifeos import backup
from lifeos.cli import main

D = dt.date(2026, 11, 18)


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    (h / "logs").mkdir(parents=True)
    (h / "now.md").write_text("# now\n", encoding="utf-8")
    (h / "logs" / "ledger.csv").write_text("date,task,model,minutes_saved,note\n2026-11-01,T,claude,5,\n", encoding="utf-8")
    (h / "logs" / "runs.jsonl").write_text('{"command":"ask"}\n', encoding="utf-8")
    return h


def test_make_copies_logs_and_writes_a_manifest_with_hashes(home, tmp_path):
    folder = backup.make(home, tmp_path / "out", today=D)
    assert folder.name == "lifeos-backup-20261118"
    man = json.loads((folder / "MANIFEST.json").read_text())
    assert set(man["files"]) == {"logs/ledger.csv", "logs/runs.jsonl"} and man["head"]
    assert backup.check(folder)["ok"]


def test_check_catches_a_changed_a_missing_and_an_extra_file(home, tmp_path):
    folder = backup.make(home, tmp_path / "out", today=D)
    (folder / "logs" / "ledger.csv").write_text("tampered\n", encoding="utf-8")
    res = backup.check(folder)
    assert not res["ok"] and any("ledger.csv" in e for e in res["errors"])
    (folder / "logs" / "runs.jsonl").unlink()
    assert any("missing" in e for e in backup.check(folder)["errors"])
    (folder / "logs" / "extra.csv").write_text("x", encoding="utf-8")
    assert any("not in the manifest" in e for e in backup.check(folder)["errors"])


def test_will_not_overwrite_or_write_inside_the_home(home, tmp_path):
    backup.make(home, tmp_path / "out", today=D)
    with pytest.raises(backup.BackupError, match="exists"):
        backup.make(home, tmp_path / "out", today=D)
    with pytest.raises(backup.BackupError, match="inside"):
        backup.make(home, home / "bk", today=D)


def test_cli(home, tmp_path, capsys):
    h = ["--home", str(home)]
    assert main(h + ["backup", "--out", str(tmp_path / "o")]) == 0
    folder = next((tmp_path / "o").iterdir())
    assert main(["backup", "--check", str(folder)]) == 0
    (folder / "logs" / "ledger.csv").write_text("bad", encoding="utf-8")
    assert main(["backup", "--check", str(folder)]) == 1


def test_restore_gives_back_identical_bytes_and_keeps_what_it_replaced(home, tmp_path):
    folder = backup.make(home, tmp_path / "out", today=D)
    original = {p.name: p.read_bytes() for p in (home / "logs").iterdir()}
    (home / "logs" / "ledger.csv").write_text("damaged", encoding="utf-8")
    (home / "logs" / "extra.csv").write_text("new", encoding="utf-8")
    aside = backup.restore(home, folder, now=dt.datetime(2026, 11, 28, 9, 0, 0))
    assert {p.name: p.read_bytes() for p in (home / "logs").iterdir()} == original
    assert aside.name == "logs.before-restore-20261128-090000"
    assert (aside / "ledger.csv").read_text() == "damaged" and (aside / "extra.csv").exists()


def test_a_backup_that_was_changed_is_refused_and_nothing_moves(home, tmp_path):
    folder = backup.make(home, tmp_path / "out", today=D)
    (folder / "logs" / "ledger.csv").write_text("tampered", encoding="utf-8")
    before = (home / "logs" / "runs.jsonl").read_bytes()
    with pytest.raises(backup.BackupError, match="does not match"):
        backup.restore(home, folder)
    assert (home / "logs" / "runs.jsonl").read_bytes() == before
    assert not list(home.glob("logs.before-restore-*"))


def test_restore_into_a_home_without_logs_works(home, tmp_path):
    import shutil
    folder = backup.make(home, tmp_path / "out", today=D)
    shutil.rmtree(home / "logs")
    assert backup.restore(home, folder) is None
    assert (home / "logs" / "runs.jsonl").exists()


def test_restore_command_reports_and_a_backup_inside_the_home_is_refused(home, tmp_path, capsys):
    folder = backup.make(home, tmp_path / "out", today=D)
    assert main(["--home", str(home), "backup", "--restore", str(folder)]) == 0
    assert "Restored" in capsys.readouterr().out
    assert main(["--home", str(home), "backup", "--restore", str(home / "logs")]) == 2


@pytest.mark.parametrize("manifest", ["{broken", "{}", '{"files": []}'])
def test_check_reports_a_malformed_manifest_instead_of_raising(tmp_path, manifest):
    folder = tmp_path / "backup"
    folder.mkdir()
    (folder / "MANIFEST.json").write_text(manifest, encoding="utf-8")
    result = backup.check(folder)
    assert not result["ok"] and result["files"] == 0
    assert "manifest" in result["errors"][0].lower()


def test_manifest_paths_cannot_escape_the_backup(tmp_path):
    folder = tmp_path / "backup"
    folder.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    digest = hashlib.sha256(outside.read_bytes()).hexdigest()
    (folder / "MANIFEST.json").write_text(json.dumps({"files": {"../outside.txt": digest}}), encoding="utf-8")
    result = backup.check(folder)
    assert not result["ok"]
    assert "unsafe path" in result["errors"][0]
