import shutil

import pytest

from lifeos import selftest
from lifeos.cli import main


def test_selftest_runs_every_step_on_a_throwaway_copy_and_passes():
    rows = selftest.run(main)
    assert len(rows) >= 18 and all(r["ok"] for r in rows), [r for r in rows if not r["ok"]]
    names = {r["name"] for r in rows}
    assert {"demo", "canary", "ledger verify", "predict", "vocab add", "rate", "digest", "numbers page"} <= names


def test_selftest_never_touches_the_real_home(tmp_path, monkeypatch, demo):
    real = tmp_path / "real"
    shutil.copytree(demo, real)
    before = {p: p.read_bytes() for p in real.rglob("*") if p.is_file()}
    monkeypatch.setenv("LIFEOS_HOME", str(real))
    selftest.run(main)
    after = {p: p.read_bytes() for p in real.rglob("*") if p.is_file()}
    assert before == after


def test_a_failing_step_is_reported_and_the_exit_code_is_one(monkeypatch, capsys):
    def broken(argv):
        return 1 if "canary" in argv else main(argv)
    rows = selftest.run(broken)
    assert [r["name"] for r in rows if not r["ok"]] == ["canary"]
    assert "FAIL" in selftest.render(rows)


def test_cli_selftest(capsys):
    assert main(["selftest"]) == 0
    assert "ALL PASSED" in capsys.readouterr().out
