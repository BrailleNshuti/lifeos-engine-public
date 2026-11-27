"""Windows write retries are counted in a local file and shown by `doctor` (round 4 item 6). Counts only, no path or content."""
import os

from lifeos import diag, store
from lifeos.cli import main


def make_home(tmp_path):
    (tmp_path / "logs").mkdir()
    (tmp_path / "now.md").write_text("# now", encoding="utf-8")
    return tmp_path


def test_a_recovered_replace_is_tallied_without_any_path(tmp_path):
    home = make_home(tmp_path)
    diag.recovered(PermissionError(13, "x"), home / "a.tmp", home / "logs" / "ratings.csv", 3)
    diag.report(PermissionError(13, "x"), home / "a.tmp", home / "logs" / "ratings.csv", 6)
    text = (home / "logs" / diag.TALLY).read_text(encoding="utf-8")
    assert [line.split()[1:] for line in text.splitlines()] == [["recovered", "3"], ["failed", "6"]]
    assert str(home) not in text and "ratings" not in text
    assert diag.stats(home)["recovered"] == 1 and diag.stats(home)["failed"] == 1


def test_a_replace_outside_a_home_writes_nothing(tmp_path):
    diag.recovered(PermissionError(13, "x"), tmp_path / "a.tmp", tmp_path / "b.txt", 2)
    assert not list(tmp_path.rglob(diag.TALLY))


def test_the_real_retry_path_tallies(tmp_path, monkeypatch):
    home = make_home(tmp_path)
    real, calls = os.replace, {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            err = PermissionError(13, "sharing violation")
            err.winerror = 32
            raise err
        return real(src, dst)
    monkeypatch.setattr(store.os, "replace", flaky)
    monkeypatch.setattr(store, "_pause", lambda s: None)
    monkeypatch.setattr(store, "_transient", lambda err: True)  # the retry is Windows-only; force it so the test runs everywhere
    store.atomic_write_bytes(home / "logs" / "x.csv", b"a,b\n")
    assert diag.stats(home)["recovered"] == 1


def test_stats_never_raises_on_a_missing_or_garbled_file(tmp_path):
    assert diag.stats(tmp_path) == {"recovered": 0, "failed": 0, "last": ""}
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / diag.TALLY).write_bytes(b"\xff\xfe nonsense\n2026-01-01 recovered 2\n")
    assert diag.stats(tmp_path)["recovered"] == 1


def test_doctor_mentions_the_retries_only_when_there_are_some(tmp_path, capsys):
    home = make_home(tmp_path)
    main(["--home", str(home), "doctor"])
    assert "windows" not in capsys.readouterr().out
    diag.recovered(PermissionError(13, "x"), home / "a.tmp", home / "logs" / "x", 2)
    main(["--home", str(home), "doctor"])
    assert "1 write(s) needed a retry" in capsys.readouterr().out
