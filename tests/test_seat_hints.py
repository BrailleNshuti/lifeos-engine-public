"""Four small things the first week of real use asked for (2026-11-26): an explicit rating kind, a hint when a seat is
sent a job it cannot do, a note when a route's review step never happened, and a shorter wait for local models."""
import pytest

from lifeos import ask, learn, seats


def test_grok_is_warned_off_shop_price_lookups():
    warn = seats.seat_warning("grok", "Find the current price and availability of a RAM stick in Germany")
    assert "shop" in warn and "block" in warn


def test_grok_gets_no_warning_for_a_plain_live_fact():
    assert seats.seat_warning("grok", "What is the latest stable release of Python 3?") == ""


def test_other_seats_get_no_shop_warning():
    assert seats.seat_warning("gemini", "Find the current price of a RAM stick") == ""


def test_an_explicit_kind_wins_over_keywords(tmp_path):
    row = learn.add_rating(tmp_path, "T-1", "gemini", 4, "private sorting and extraction", kind="document review")
    assert row["kind"] == "document review"
    again = learn.add_rating(tmp_path, "T-2", "gemini", 4, "private sorting and extraction")
    assert "Qwen" in again["kind"]  # no explicit kind: the old keyword routing still applies


def test_an_explicit_kind_is_trimmed_and_cleaned(tmp_path):
    row = learn.add_rating(tmp_path, "T-3", "codex", 3, "x", kind="  code\nreview, with a very long name " + "x" * 200)
    assert "\n" not in row["kind"] and len(row["kind"]) <= 80 and "," not in row["kind"]


@pytest.mark.parametrize("cmd0,expected", [("ollama", ask.LOCAL_TIMEOUT), ("grok", ask.TIMEOUT), ("codex", ask.TIMEOUT)])
def test_local_models_get_a_shorter_wait(cmd0, expected, monkeypatch):
    monkeypatch.delenv("LIFEOS_TIMEOUT", raising=False)
    assert ask.call_timeout(cmd0) == expected


def test_the_environment_still_overrides_every_wait(monkeypatch):
    monkeypatch.setenv("LIFEOS_TIMEOUT", "900")
    assert ask.call_timeout("ollama") == 900 and ask.call_timeout("grok") == 900


def test_review_note_when_the_route_names_a_review_that_never_ran():
    task = "---\nroute: Claude Code -> Codex review\n---\n## Result · gemini · 2026-11-26\nanswer\n"
    assert "review" in learn.review_note(task)
    done = task + "\n## Result · review:codex · 2026-11-26\nok\n"
    assert learn.review_note(done) == ""
    assert learn.review_note("---\nroute: me\n---\nbody") == ""


def test_cli_rate_uses_a_kind_line_and_warns_about_a_missing_review(tmp_path, demo, capsys, monkeypatch):
    import shutil
    from lifeos.cli import main
    home = tmp_path / "home"
    shutil.copytree(demo, home)
    task = next((home / "tasks").glob("T-261116*.md"))
    raw = task.read_text(encoding="utf-8").replace("status: doing", "status: doing\nkind: document review", 1)
    task.write_text(raw, encoding="utf-8")
    monkeypatch.setenv("LIFEOS_HOME", str(home))
    assert main(["rate", "T-261116", "claude", "4"]) == 0
    captured = capsys.readouterr()
    assert "document review" in captured.out
    assert "review step" in captured.err  # the demo route names a Codex review and the file holds none
