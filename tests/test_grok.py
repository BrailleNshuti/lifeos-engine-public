"""The locked Grok seat: live facts only, no tools, no memory, own token share. No model is called."""
import datetime as dt
import json

import pytest

from lifeos import ask, policy, seats

NOW = dt.datetime(2026, 11, 17, 12, 0, tzinfo=dt.timezone.utc)


def test_live_facts_go_to_grok_and_long_reading_stays_with_gemini():
    assert seats.pick("What is the latest price of the laptop")[0] == "grok"
    assert seats.pick("Any news on the IU exam dates today")[0] == "grok"
    assert seats.pick("Read all of this long pdf")[0] == "gemini"


def test_grok_is_a_remote_seat_with_its_own_share_beside_gemini():
    assert "grok" in seats.REMOTE and policy.provider_locality("grok") == "remote"
    assert seats.SHARES["grok"] == 20_000 and seats.SHARES["gemini"] == 30_000
    plan = seats.budget([{"command": "ask", "model": "grok", "status": "ok", "date": "2026-11-17",
                          "tokens": 20_000, "finished_at": "2026-11-17T10:00:00Z"}], NOW)
    assert plan["seats"]["grok"]["used"] == 20_000 and plan["seats"]["gemini"]["used"] == 0


def test_grok_is_replaced_by_gemini_then_the_others_then_local():
    _model, _reason, chain = seats.choose("latest news today", "PERSONAL", {})
    assert chain == ["grok", "gemini", "claude", "codex", "qwen", "ollama"]
    _model, _reason, chain = seats.choose("latest news today", "PERSONAL", {"grok": "usage limit"})
    assert chain[0] == "gemini"


@pytest.mark.parametrize("tier", ["SENSITIVE", "SECRET"])
@pytest.mark.parametrize("explicit", [None, "grok"])
def test_a_sensitive_task_never_selects_grok(tier, explicit):
    model, _reason, chain = seats.choose("what is the latest price of my bank csv", tier, {}, explicit=explicit)
    assert "grok" not in chain and model in ("qwen", "ollama")


def test_the_seat_is_locked(monkeypatch):
    seen = {}

    def fake(cmd, prompt, **kwargs):
        seen.update(cmd=cmd, prompt=prompt, kwargs=kwargs)
        return json.dumps({"text": "Price is 499 EUR (source: shop, 2026-11-17)."})

    monkeypatch.setattr(ask, "_run_cli", fake)
    assert ask.ask_grok("latest price?") == "Price is 499 EUR (source: shop, 2026-11-17)."
    cmd = seen["cmd"]
    assert cmd[0] == "grok" and "-p" in cmd and cmd[cmd.index("--output-format") + 1] == "json"
    for flag in ("--no-auto-update", "--no-plan", "--no-subagents", "--no-memory"):
        assert flag in cmd
    assert "--always-approve" not in cmd  # nothing runs on this computer without a yes
    assert seen["kwargs"].get("use_review_cwd") is False  # an empty temp folder, never the repo
    assert "latest price?" in cmd and seen["kwargs"].get("via_stdin") is False


def test_a_prompt_too_long_for_the_command_line_is_refused_not_cut(monkeypatch):
    monkeypatch.setattr(ask, "_run_cli", lambda *a, **k: pytest.fail("must not run"))
    with pytest.raises(ask.AskError, match="too long"):
        ask.ask_grok("x" * 30_000)


@pytest.mark.parametrize("raw,message", [
    ("not json", "grok failed"),
    (json.dumps({"something": "else"}), "grok failed"),
    (json.dumps({"text": ""}), "empty"),
    (json.dumps({"error": "usage limit reached"}), "usage limit"),
])
def test_bad_output_is_an_error_not_an_answer(monkeypatch, raw, message):
    monkeypatch.setattr(ask, "_run_cli", lambda *a, **k: raw)
    with pytest.raises(ask.AskError, match=message):
        ask.ask_grok("latest news?")


def test_grok_is_registered_for_the_provider_table_and_adapters():
    assert ask.ADAPTERS["grok"] is ask.ask_grok
    assert ask.PROVIDERS["grok"]["locality"] == "remote" and ask.PROVIDERS["grok"]["binary"] == "grok"


def test_grok_never_gets_the_full_pack_because_its_prompt_travels_in_argv():
    allowed, why = policy.check_provider_allowed("PERSONAL", "grok", full=True)
    assert not allowed and "command line" in why
    assert policy.check_provider_allowed("PERSONAL", "grok", full=False)[0]


def test_sensitive_never_selects_grok_even_for_live_fact_wording():
    for explicit in (None, "grok"):
        _m, _r, chain = seats.choose("latest price today", "SENSITIVE", {}, explicit=explicit)
        assert "grok" not in chain


def test_a_strange_digit_in_the_timeout_does_not_crash(monkeypatch):
    monkeypatch.setenv("LIFEOS_TIMEOUT", "²")
    assert ask.timeout_seconds() == ask.TIMEOUT
