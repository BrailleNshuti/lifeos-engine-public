import datetime as dt
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
