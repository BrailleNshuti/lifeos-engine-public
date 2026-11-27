"""`delegate` moves a seat that has no tool for the job behind the seats that do (a hint becomes a choice).
An explicit seat is never moved, and a private task never gets a cloud seat."""
import shutil

import pytest

from lifeos import delegate, seats

SHOP_TEXT = "Find the current price and availability of a RAM stick in a shop"


def test_reroute_moves_a_seat_without_the_tool_behind_one_with_it():
    chain, note = seats.reroute(["grok", "gemini", "claude", "qwen", "ollama"], SHOP_TEXT)
    assert chain[0] == "gemini" and "grok" in note and chain.index("grok") > chain.index("gemini")
    assert sorted(chain) == sorted(["grok", "gemini", "claude", "qwen", "ollama"])  # nothing added, nothing dropped


def test_reroute_keeps_the_order_of_the_others():
    chain, _ = seats.reroute(["grok", "gemini", "claude", "codex"], SHOP_TEXT)
    assert chain == ["gemini", "claude", "codex", "grok"]


def test_nothing_changes_when_the_first_seat_can_do_the_job():
    chain, note = seats.reroute(["grok", "gemini"], "What is the latest stable release of Python 3?")
    assert chain == ["grok", "gemini"] and note == ""


def test_nothing_changes_when_every_seat_lacks_the_tool():
    chain, note = seats.reroute(["qwen", "ollama"], "what is the price of bitcoin today")
    assert chain == ["qwen", "ollama"] and note == ""


def test_a_single_seat_chain_is_left_alone():
    assert seats.reroute(["grok"], SHOP_TEXT) == (["grok"], "")


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    task = target / "tasks" / "T-261116-demo-cli.md"
    raw = task.read_text(encoding="utf-8").replace("Ship the context command", "Find current shop prices and availability")
    task.write_text(raw, encoding="utf-8")
    return target


def fakes():
    return {name: (lambda prompt, name=name: f"ANSWER FROM {name}") for name in seats.CHAINS}


def test_delegate_prefers_a_seat_with_the_tool_and_says_why(home):
    out = delegate.run_delegate(home, "T-261116", adapters=fakes(), dry_run=True)
    assert out["chain"][0] != "grok"
    assert "rerouted" in out["reason"].lower() or "no tool" in out["reason"].lower()


def test_an_explicit_seat_is_never_rerouted(home):
    out = delegate.run_delegate(home, "T-261116", model="grok", adapters=fakes(), dry_run=True)
    assert out["chain"][0] == "grok"


def test_a_private_task_chain_stays_local_after_a_reroute(home):
    task = home / "tasks" / "T-261116-demo-cli.md"
    task.write_text(task.read_text(encoding="utf-8").replace("Find current shop prices", "Sort my bank csv: find current shop prices"), encoding="utf-8")
    out = delegate.run_delegate(home, "T-261116", adapters=fakes(), dry_run=True)
    assert set(out["chain"]) <= {"qwen", "ollama"}
