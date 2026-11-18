import json

import pytest

from lifeos import canary, guard
from lifeos.cli import main


def test_guard_score_is_complete_and_has_no_false_alarms():
    score = canary.guard_score()
    assert score["total"] >= 300
    assert score["blocked"] == score["total"] and score["misses"] == []
    assert score["benign_flagged"] == [] and score["benign_total"] >= 7


def test_the_score_is_real_it_drops_when_the_guard_is_blind(monkeypatch):
    monkeypatch.setattr(guard, "scan_text", lambda *a, **k: [])
    monkeypatch.setattr(canary, "scan_text", lambda *a, **k: [])
    score = canary.guard_score()
    assert score["blocked"] == 0 and len(score["misses"]) == score["total"]


def test_the_score_is_deterministic():
    assert canary.canaries() == canary.canaries()
    assert canary.canaries(seed=1) != canary.canaries(seed=2)


def test_outbound_canaries_are_stopped_before_any_model_is_called():
    out = canary.outbound_check()
    assert out["ok"], out
    assert out["model_calls"] == 0
    assert out["kinds_stopped"] >= 4 and out["leaked_into_logs"] == []


def test_cli_prints_the_score_and_exits_zero(capsys):
    assert main(["canary"]) == 0
    text = capsys.readouterr().out
    assert "Guard score:" in text and "Outbound canaries:" in text
    assert main(["canary", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["guard"]["misses"] == []
