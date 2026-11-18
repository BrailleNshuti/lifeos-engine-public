import datetime as dt
import json
import shutil

import pytest

from lifeos import ask, panel
from lifeos.cli import main

TODAY = dt.date(2026, 11, 20)


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


class Fake:
    def __init__(self, answer):
        self.answer, self.prompts = answer, []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.answer


A = "- Use sqlite for the store\n- Add tests first\n- Rename the config file\n- The limit is 14 calls"
B = "- Use sqlite for the store\n- Add tests first\n- Delete the old cache folder\n- The limit is 15 calls"
C = "- Use sqlite for the store\n- Add tests first\n- Rename config file\n- The limit is 14 calls"


def run(home, **kw):
    fakes = {"claude": Fake(A), "codex": Fake(B), "gemini": Fake(C)}
    out = panel.run_panel(home, ["claude", "codex", "gemini"], "T-261116", adapters=fakes, today=TODAY, **kw)
    return out, fakes


def test_every_model_gets_the_same_input_and_never_sees_another_answer(home):
    out, fakes = run(home)
    prompts = [f.prompts[0] for f in fakes.values()]
    assert prompts[0] == prompts[1] == prompts[2]
    assert not any("Delete the old cache" in p or "sqlite" in p for p in prompts)
    shas = {r["context_sha256"] for r in map(json.loads, (home / "logs" / "runs.jsonl").read_text(encoding="utf-8").splitlines())
            if r.get("command") == "ask"}
    assert len(shas) == 1 and out["pack_sha256"] in shas


def test_all_answers_are_recorded_and_replay_still_matches(home):
    out, _ = run(home)
    task = next((home / "tasks").glob("T-261116*.md")).read_text(encoding="utf-8")
    assert task.count("## Result · ") >= 3
    from lifeos import replay
    assert all(replay.replay_run(home, rid)["identical"] for rid in out["run_ids"].values())


def test_report_separates_agreement_conflict_and_single_voice(home):
    out, _ = run(home)
    rep = out["report"]
    agreed = " | ".join(c["text"] for c in rep["agreed_by_all"])
    assert "sqlite" in agreed and "tests" in agreed
    assert len(rep["conflicts"]) == 1 and {"claude", "codex"} <= set(rep["conflicts"][0]["models"])
    assert [c["models"] for c in rep["single"]] == [["codex"]] and "cache" in rep["single"][0]["text"]
    assert any(set(c["models"]) == {"claude", "gemini"} for c in rep["majority"])


def test_report_is_written_to_the_task_file(home):
    run(home)
    task = next((home / "tasks").glob("T-261116*.md")).read_text(encoding="utf-8")
    assert "## Panel · 2026-11-20" in task and "Conflicts" in task and "no model saw another" in task.lower()


def test_one_failing_model_does_not_stop_the_panel(home):
    def boom(prompt):
        raise ask.AskError("provider down")
    fakes = {"claude": Fake(A), "codex": boom, "gemini": Fake(C)}
    out = panel.run_panel(home, ["claude", "codex", "gemini"], "T-261116", adapters=fakes, today=TODAY)
    assert out["failed"] == {"codex": "provider down"} and set(out["run_ids"]) == {"claude", "gemini"}


def test_a_panel_needs_two_to_four_known_models(home):
    with pytest.raises(panel.PanelError, match="two to four"):
        panel.run_panel(home, ["claude"], "T-261116", adapters={"claude": Fake(A)}, today=TODAY)
    with pytest.raises(panel.PanelError, match="two to four"):
        panel.run_panel(home, list("abcde"), "T-261116", adapters={}, today=TODAY)
    with pytest.raises(panel.PanelError, match="Unknown"):
        panel.run_panel(home, ["claude", "nope"], "T-261116", adapters={"claude": Fake(A)}, today=TODAY)
    with pytest.raises(panel.PanelError, match="twice"):
        panel.run_panel(home, ["claude", "claude"], "T-261116", adapters={"claude": Fake(A)}, today=TODAY)


def test_claim_matching_ignores_wording_but_not_numbers_or_negation():
    assert panel.same_topic("Add tests first", "add the tests first!")
    assert panel.conflicting("The limit is 14 calls", "The limit is 15 calls")
    assert panel.conflicting("Never push to main", "Push to main")
    assert not panel.conflicting("Use sqlite for the store", "Use sqlite for the store")


def test_cli_panel(home, capsys, monkeypatch):
    monkeypatch.setenv("LIFEOS_HOME", str(home))
    monkeypatch.setitem(ask.ADAPTERS, "claude", Fake(A))
    monkeypatch.setitem(ask.ADAPTERS, "codex", Fake(B))
    assert main(["panel", "T-261116", "--models", "claude,codex"]) == 0
    text = capsys.readouterr().out
    assert "Panel" in text and "Conflicts" in text
    assert main(["panel", "T-261116", "--models", "claude"]) == 2
