import datetime as dt
import shutil

import pytest

from lifeos import learn, seats
from lifeos.cli import main

TODAY = dt.date(2026, 11, 21)
CODE = "implement a python module"  # seats.kind -> claude writes code
OTHER = "decide the plan for next week"


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def rate(home, model, score, text=CODE, task="T-261116", note=""):
    return learn.add_rating(home, task, model, score, text, today=TODAY, note=note)


def test_rating_is_stored_with_its_kind(home):
    row = rate(home, "claude", 4)
    assert row["kind"] == seats.kind(CODE)[3] and row["score"] == 4
    assert (home / "logs" / "ratings.csv").read_text().splitlines()[0] == "date,task,model,score,kind,note"


@pytest.mark.parametrize("model,score", [("nobody", 3), ("claude", 0), ("claude", 6)])
def test_bad_rating_is_refused(home, model, score):
    with pytest.raises(learn.LearnError):
        rate(home, model, score)


def test_note_with_private_data_is_refused(home):
    with pytest.raises(learn.LearnError):
        rate(home, "claude", 3, note="key sk-ant-api03-" + "a1B2c3D4" * 5)


def test_no_recommendation_with_too_little_evidence(home):
    for s in (5, 5):
        rate(home, "codex", s)
    rec = learn.recommend(home, CODE)
    assert rec["model"] is None and "3" in rec["why"]


def test_recommends_the_clearly_better_model(home):
    for s in (2, 3, 2):
        rate(home, "claude", s)
    for s in (5, 4, 5):
        rate(home, "codex", s)
    rec = learn.recommend(home, CODE)
    assert rec["model"] == "codex" and rec["gap"] >= 1


def test_a_small_gap_keeps_the_default(home):
    for s in (4, 4, 4):
        rate(home, "claude", s)
    for s in (4, 5, 4):
        rate(home, "codex", s)
    assert learn.recommend(home, CODE)["model"] is None


def test_ratings_of_another_kind_do_not_count(home):
    for s in (5, 5, 5):
        rate(home, "codex", s, text=OTHER)
    assert learn.recommend(home, CODE)["model"] is None


def test_report_lists_each_kind(home):
    rate(home, "claude", 4)
    rep = learn.report(home)
    assert rep[seats.kind(CODE)[3]]["claude"] == {"n": 1, "mean": 4.0}


def test_cli_rate_and_learn(home, capsys, monkeypatch):
    monkeypatch.setenv("LIFEOS_HOME", str(home))
    assert main(["rate", "T-261116", "claude", "4", "--note", "clean diff"]) == 0
    assert main(["rate", "T-261116", "claude", "9"]) == 2
    capsys.readouterr()
    assert main(["learn"]) == 0
    assert "claude" in capsys.readouterr().out
    assert main(["learn", "--json"]) == 0


def test_delegate_learned_follows_clear_ratings_only(home, demo):
    from lifeos import delegate
    text = delegate.task_text(delegate.task_file(home, "T-261116"))
    plain = delegate.run_delegate(home, "T-261116", dry_run=True, adapters={"claude": 1, "codex": 1, "gemini": 1})
    for s in (1, 2, 1):
        learn.add_rating(home, "T-261116", plain["model"], s, text, today=TODAY)
    other = "codex" if plain["model"] != "codex" else "claude"
    for s in (5, 5, 4):
        learn.add_rating(home, "T-261116", other, s, text, today=TODAY)
    out = delegate.run_delegate(home, "T-261116", dry_run=True, learned=True, adapters={"claude": 1, "codex": 1, "gemini": 1})
    assert out["model"] == other and out["reason"].startswith("learned")
    again = delegate.run_delegate(home, "T-261116", dry_run=True, adapters={"claude": 1, "codex": 1, "gemini": 1})
    assert again["model"] == plain["model"]
