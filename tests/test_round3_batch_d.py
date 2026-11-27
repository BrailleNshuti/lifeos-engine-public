"""Round 3 items 11, 14, 19, 23, 25 and 26: more guard shapes, an egress share warning, a Grok URL hint, an answer length
flag, `lifeos help-me`, and completion covering every command."""
import datetime as dt
import json
import shutil
from pathlib import Path

import pytest

from lifeos import check, egress, seats
from lifeos.cli import build_parser, main
from lifeos.completion import script
from lifeos.guard import scan_text

ROOT = Path(__file__).resolve().parents[1]
BASIC = "QWxhZGRpbjpvcGVuIHNlc2FtZQ" + "AAAAAAAA"  # base64-looking, made up
HEX40 = "a1b2c3d4e5" * 4
TODAY = dt.date(2026, 11, 27)


def blocked(text):
    return [f for f in scan_text(text) if f[1] == "BLOCK"]


# 11. guard
@pytest.mark.parametrize("text", [f"Authorization: Basic {BASIC}", f"curl -H 'authorization: basic {BASIC}' https://x.example",
                                  f"key={HEX40}", f"secret: {HEX40}", f"client_secret = {HEX40}"])
def test_more_secret_shapes_are_blocked(text):
    assert blocked(text), text


@pytest.mark.parametrize("text", ["key=value", "the key idea is simple", "sha256 " + "ab" * 32, f"commit {HEX40} merged",
                                  "Basic authentication is explained in the docs", "secret santa on 2026-12-24", "key=12345"])
def test_look_alikes_are_not_blocked(text):
    assert not blocked(text), text


# 14. egress share warning
def write_runs(home, records):
    (home / "logs").mkdir(exist_ok=True)
    (home / "logs" / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def test_a_seat_over_its_weekly_share_is_warned_about(tmp_path):
    write_runs(tmp_path, [{"command": "ask", "model": "grok", "tokens": 21000, "status": "ok", "date": "2026-11-26"},
                          {"command": "ask", "model": "claude", "tokens": 100, "status": "ok", "date": "2026-11-26"}])
    warnings = egress.over_share(tmp_path, today=TODAY)
    assert len(warnings) == 1 and "grok" in warnings[0] and "21,000" in warnings[0] and "20,000" in warnings[0]


def test_old_tokens_do_not_count_toward_the_weekly_share(tmp_path):
    write_runs(tmp_path, [{"command": "ask", "model": "grok", "tokens": 90000, "status": "ok", "date": "2026-11-01"}])
    assert egress.over_share(tmp_path, today=TODAY) == []


def test_the_cli_prints_the_warning(tmp_path, demo, capsys, monkeypatch):
    home = tmp_path / "home"
    shutil.copytree(demo, home)
    write_runs(home, [{"command": "ask", "model": "grok", "tokens": 25000, "status": "ok", "date": dt.date.today().isoformat()}])
    monkeypatch.setenv("LIFEOS_HOME", str(home))
    assert main(["egress"]) == 0
    assert "WARNING" in capsys.readouterr().out


# 19. grok URL hint
@pytest.mark.parametrize("text", ["fetch http://example.org/page", "open http://localhost:8080/admin", "read https://192.168.1.5/router",
                                  "get https://10.0.0.7/x", "https://127.0.0.1:9000"])
def test_grok_is_warned_about_non_public_or_plain_http_urls(text):
    assert "public https" in seats.seat_warning("grok", text)


def test_a_public_https_url_gets_no_url_warning():
    assert "public https" not in seats.seat_warning("grok", "fetch https://www.python.org/downloads/")


# 23. answer length flag
def test_a_very_long_answer_is_flagged():
    long_text = "word " * 2000 + " Next step: shorten."
    assert any("very long" in f for f in check.check_answer(long_text))


def test_a_normal_answer_is_not_flagged_for_length():
    assert not any("very long" in f for f in check.check_answer("Result 42 from https://x.org 2026-11-27. Next step: none."))


# 25. help-me
def test_help_me_prints_the_loop(capsys):
    assert main(["help-me"]) == 0
    out = capsys.readouterr().out
    for word in ("task new", "--dry-run", "CHECK", "rate", "sunday"):
        assert word in out


def test_help_me_matches_the_daily_guide():
    guide = (ROOT / "docs" / "DAILY.md").read_text(encoding="utf-8")
    for command in ("lifeos task new", "lifeos ask", "lifeos rate"):
        assert command in guide


# 26. completion covers every command, in both shells
@pytest.mark.parametrize("shell", ["bash", "powershell"])
def test_completion_names_every_command(shell):
    parser = build_parser()
    text = script(shell, parser)
    commands = next(a for a in parser._actions if getattr(a, "choices", None) and "task" in a.choices).choices
    missing = [name for name in commands if name not in text]
    assert not missing, missing
