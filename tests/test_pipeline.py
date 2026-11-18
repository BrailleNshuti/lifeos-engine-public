import json

import pytest

from lifeos import pipeline
from lifeos.cli import main


def make(home, steps, name="check"):
    d = home / "pipelines"
    d.mkdir(exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps({"name": name, "steps": steps}), encoding="utf-8")


def test_dry_run_lists_steps_and_runs_nothing(tmp_path):
    make(tmp_path, [{"name": "a", "argv": ["week"]}, {"name": "b", "argv": ["seats"]}])
    calls = []
    out = pipeline.run(tmp_path, "check", lambda argv: calls.append(argv) or 0, execute=False)
    assert calls == [] and [r["status"] for r in out] == ["planned", "planned"]


def test_run_stops_at_the_first_failing_gate(tmp_path):
    make(tmp_path, [{"name": "a", "argv": ["x"]}, {"name": "b", "argv": ["y"]}, {"name": "c", "argv": ["z"]}])
    calls = []

    def runner(argv):
        calls.append(argv[-1])
        return 1 if argv[-1] == "y" else 0
    out = pipeline.run(tmp_path, "check", runner, execute=True)
    assert calls == ["x", "y"]
    assert [r["status"] for r in out] == ["ok", "failed", "skipped"]


def test_continue_gate_lets_the_flow_go_on(tmp_path):
    make(tmp_path, [{"name": "a", "argv": ["x"], "gate": "continue"}, {"name": "b", "argv": ["y"]}])
    out = pipeline.run(tmp_path, "check", lambda argv: 1 if argv[-1] == "x" else 0, execute=True)
    assert [r["status"] for r in out] == ["failed", "ok"]


def test_bad_files_are_refused(tmp_path):
    with pytest.raises(pipeline.PipelineError, match="No pipeline"):
        pipeline.load(tmp_path, "nope")
    make(tmp_path, [], name="empty")
    with pytest.raises(pipeline.PipelineError, match="no steps"):
        pipeline.load(tmp_path, "empty")
    make(tmp_path, [{"name": "n", "argv": "week"}], name="bad")
    with pytest.raises(pipeline.PipelineError, match="argv"):
        pipeline.load(tmp_path, "bad")
    (tmp_path / "pipelines" / "../x.json").parent.mkdir(exist_ok=True)
    with pytest.raises(pipeline.PipelineError, match="name"):
        pipeline.load(tmp_path, "../x")


def test_a_pipeline_cannot_nest_or_hold_secrets(tmp_path):
    make(tmp_path, [{"name": "n", "argv": ["pipeline", "run", "check"]}], name="loop")
    with pytest.raises(pipeline.PipelineError, match="nest"):
        pipeline.load(tmp_path, "loop")
    make(tmp_path, [{"name": "n", "argv": ["ask", "claude", "sk-ant-api03-" + "a1B2c3D4" * 5]}], name="key")
    with pytest.raises(pipeline.PipelineError, match="private"):
        pipeline.load(tmp_path, "key")


def test_cli_dry_run_then_run(tmp_path, capsys):
    (tmp_path / "now.md").write_text("# now\n", encoding="utf-8")
    make(tmp_path, [{"name": "seats", "argv": ["seats"]}])
    assert main(["--home", str(tmp_path), "pipeline", "check"]) == 0
    assert "planned" in capsys.readouterr().out
    assert main(["--home", str(tmp_path), "pipeline", "check", "--run"]) == 0
    assert main(["--home", str(tmp_path), "pipeline", "missing"]) == 2


def test_steps_run_with_the_home_as_working_folder_and_it_is_restored(tmp_path):
    import os
    before = os.getcwd()
    make(tmp_path, [{"name": "a", "argv": ["x"]}])
    seen = []
    pipeline.run(tmp_path, "check", lambda argv: seen.append(os.getcwd()) or 0, execute=True)
    assert seen == [str(tmp_path.resolve())] and os.getcwd() == before
