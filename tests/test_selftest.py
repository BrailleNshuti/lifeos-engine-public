import shutil

import pytest

from lifeos import selftest
from lifeos.cli import main


def test_selftest_runs_every_step_on_a_throwaway_copy_and_passes():
    rows = selftest.run(main)
    assert len(rows) >= 18 and all(r["ok"] for r in rows), [r for r in rows if not r["ok"]]
    names = {r["name"] for r in rows}
    assert {"demo", "canary", "ledger verify", "predict", "vocab add", "rate", "digest", "numbers page"} <= names


def test_a_debate_round_trip_runs_offline_and_keeps_the_ledger_chain_intact():
    rows = selftest.run(main)
    assert len(rows) == len(selftest.STEPS) + selftest.DEBATE_STEPS
    names = [r["name"] for r in rows]
    for name in ("debate start", "debate record claude", "debate record codex", "debate next", "debate score", "debate run dry",
                 "ledger verify after debate"):
        assert name in names and next(r for r in rows if r["name"] == name)["ok"], name


def test_the_readme_states_the_real_number_of_steps():
    import re
    from pathlib import Path
    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
    claimed = int(re.search(r"lifeos selftest.*?Runs (\d+) steps", readme).group(1))
    assert claimed == len(selftest.STEPS) + selftest.DEBATE_STEPS


def test_a_failing_debate_step_is_named_and_the_rest_still_run():
    def broken(argv):
        return 1 if "debate" in argv and "score" in argv else main(argv)
    failed = [r["name"] for r in selftest.run(broken) if not r["ok"]]
    assert failed == ["debate score"]


def test_if_the_debate_cannot_start_every_debate_step_is_reported_not_dropped():
    def no_debate(argv):
        return 1 if "start" in argv and "debate" in argv else main(argv)
    rows = selftest.run(no_debate)
    assert len(rows) == len(selftest.STEPS) + selftest.DEBATE_STEPS
    assert [r["name"] for r in rows if not r["ok"]][0] == "debate start"
    assert sum(not r["ok"] for r in rows) == selftest.DEBATE_STEPS


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
