import datetime as dt
import shutil

import pytest

from lifeos import ask, demo, numbers, savings
from lifeos.cli import main

D = dt.date(2026, 11, 30)


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def test_savings_compares_sent_tokens_with_pasting_every_note(home):
    ask.run_ask(home, "claude", "T-261116", adapters={"claude": lambda p: "ok"}, today=D)
    ask.run_ask(home, "claude", "T-261116", adapters={"claude": lambda p: "ok"}, today=D)
    s = savings.compute(home)
    assert s["runs"] == 2 and s["sent"] > 0
    assert s["baseline_each"] >= s["sent"] / 2
    assert s["saved"] == s["baseline_each"] * 2 - s["sent"]
    assert 0 <= s["percent"] <= 100 and "pasting" in savings.render(s).lower()


def test_savings_with_no_runs_says_so(home):
    assert savings.compute(home)["runs"] == 0
    assert "No ask runs" in savings.render(savings.compute(home))


def test_local_and_review_runs_are_not_counted(home):
    log = home / "logs" / "runs.jsonl"
    log.parent.mkdir(exist_ok=True)
    log.write_text('{"command":"ask","model":"qwen","locality":"local","tokens":50,"status":"ok"}\n'
                   '{"command":"review","model":"review","tokens":99,"status":"ok"}\n')
    assert savings.compute(home)["runs"] == 0


def test_demo_tells_the_whole_story_on_made_up_data():
    steps = demo.run()
    names = [s["step"] for s in steps]
    assert names == ["guard blocks a fake secret", "blind panel finds a conflict", "ledger stays tamper-evident",
                     "replay proves the input", "a cut tail is caught by the anchor"]
    assert all(s["ok"] for s in steps)


def test_html_page_is_self_contained_and_has_no_home_text(home):
    page = numbers.render_html(numbers.build(home, commands=3), today=D)
    assert page.startswith("<!doctype html>") and "<script" not in page and "http" not in page
    assert "Engine in numbers" in page and str(home) not in page


def test_cli_savings_demo_and_html(home, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LIFEOS_HOME", str(home))
    assert main(["savings"]) == 0
    assert main(["demo"]) == 0
    assert "tamper" in capsys.readouterr().out
    out = tmp_path / "n.html"
    assert main(["numbers", "--html", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_honest_labels_say_ceiling_and_show_the_measured_average(home):
    for _ in range(2):
        ask.run_ask(home, "claude", "T-261116", adapters={"claude": lambda p: "ok"}, today=D)
    s = savings.compute(home)
    assert s["avg_sent"] == round(s["sent"] / 2)
    text = savings.render(s)
    assert "measured" in text and "Ceiling" in text
    page = numbers.render_html(numbers.build(home, commands=3), today=D)
    assert "worst-case baseline" in page and "per cloud run" in page
    assert "worst-case baseline" in numbers.render(numbers.build(home, commands=3), today=D)
