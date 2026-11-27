import datetime as dt
import shutil

import pytest

from lifeos import ask, cli, seats
from lifeos.store import read_run_records

QUOTA = "Individual quota reached. Please upgrade your subscription to increase your limits. Resets in 78h40m32s."


@pytest.fixture
def home(tmp_path, demo, monkeypatch):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    monkeypatch.setattr(ask.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(ask, "_probe_ollama_tags", lambda: {"qwen3.5:4b", "llama3.2"})
    return target


def adapters(**broken):
    def make(name):
        def call(prompt):
            if name in broken:
                raise ask.AskError(broken[name])
            return "OK"
        return call
    return {name: make(name) for name in ask.PROVIDERS}


def smoke(home, monkeypatch, capsys, extra=(), **broken):
    monkeypatch.setattr(ask, "ADAPTERS", adapters(**broken))
    code = cli.main(["--home", str(home), "doctor", "--smoke", *extra])
    return code, capsys.readouterr().out


def test_a_usage_limit_probe_prints_the_reason_and_records_a_rest(home, monkeypatch, capsys):
    code, out = smoke(home, monkeypatch, capsys, gemini=QUOTA)
    assert "resting" in out and "Resets in 78h40m32s" in out
    assert code == 0 and "doctor: ok" in out  # a seat that hit its limit is resting, not broken
    rows = [r for r in read_run_records(home) if r.get("command") == "smoke"]
    assert [(r["model"], r["status"]) for r in rows] == [("gemini", "failed")]
    assert rows[0]["tokens"] == 0 and "quota reached" in rows[0]["error"].lower()
    now = dt.datetime.now(dt.timezone.utc)
    assert seats.pressure(read_run_records(home), now)["gemini"].startswith("usage limit until")


def test_an_out_of_credits_probe_is_resting_and_not_retried(home, monkeypatch, capsys):
    code, out = smoke(home, monkeypatch, capsys, grok="HTTP 402: out of credits")
    assert code == 0 and "resting" in out and "out of credits" in out
    assert seats.pressure(read_run_records(home), dt.datetime.now(dt.timezone.utc))["grok"] == (
        "out of credits; add credits before retrying"
    )

    called = []
    monkeypatch.setattr(ask, "ADAPTERS", {
        name: (lambda prompt, name=name: called.append(name) or "OK") for name in ask.PROVIDERS
    })
    assert cli.main(["--home", str(home), "doctor", "--smoke"]) == 0
    capsys.readouterr()
    assert "grok" not in called


def test_a_smoke_record_never_counts_as_spend(home, monkeypatch, capsys):
    smoke(home, monkeypatch, capsys, gemini=QUOTA)
    now = dt.datetime.now(dt.timezone.utc)
    plan = seats.budget(read_run_records(home), now)
    assert plan["used_calls"] == 0 and plan["used_tokens"] == 0


def test_other_failures_print_a_short_redacted_reason_and_record_nothing(home, monkeypatch, capsys):
    mail = "someone" + "@" + "example.org"
    secret = "pass" + "word=" + "x1y2z3" * 3
    code, out = smoke(home, monkeypatch, capsys, grok=f"boom for {mail} {secret}")
    assert code == 1 and "doctor: 1 thing(s) to fix" in out
    assert "boom" in out and mail not in out and "x1y2z3" not in out
    assert not [r for r in read_run_records(home) if r.get("command") == "smoke"]


def test_a_resting_seat_is_not_called_again(home, monkeypatch, capsys):
    smoke(home, monkeypatch, capsys, gemini=QUOTA)
    called = []
    live = adapters()

    def spy(name):
        def call(prompt):
            called.append(name)
            return live[name](prompt)
        return call

    monkeypatch.setattr(ask, "ADAPTERS", {name: spy(name) for name in ask.PROVIDERS})
    assert cli.main(["--home", str(home), "doctor", "--smoke"]) == 0
    out = capsys.readouterr().out
    assert "gemini" not in called and "grok" in called
    assert "usage limit until" in out


def test_only_limits_the_probe_to_named_seats(home, monkeypatch, capsys):
    called = []
    monkeypatch.setattr(ask, "ADAPTERS", {n: (lambda p, n=n: called.append(n) or "OK") for n in ask.PROVIDERS})
    assert cli.main(["--home", str(home), "doctor", "--smoke", "--only", "grok,qwen"]) == 0
    capsys.readouterr()
    assert sorted(called) == ["grok", "qwen"]


def test_only_rejects_an_unknown_seat(home, monkeypatch, capsys):
    monkeypatch.setattr(ask, "ADAPTERS", adapters())
    assert cli.main(["--home", str(home), "doctor", "--smoke", "--only", "nope"]) == 2
    assert "unknown seat" in capsys.readouterr().err.lower()


def test_the_probe_names_each_seat_before_calling_it(home, monkeypatch, capsys):
    monkeypatch.setattr(ask, "ADAPTERS", adapters())
    cli.main(["--home", str(home), "doctor", "--smoke", "--only", "grok"])
    assert "probing grok" in capsys.readouterr().err


def test_a_home_without_logs_still_prints_and_says_the_rest_was_not_saved(tmp_path, demo, monkeypatch, capsys):
    target = tmp_path / "bare"
    shutil.copytree(demo, target)
    shutil.rmtree(target / "logs")
    monkeypatch.setattr(ask.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(ask, "_probe_ollama_tags", lambda: {"qwen3.5:4b", "llama3.2"})
    monkeypatch.setattr(ask, "ADAPTERS", adapters(gemini=QUOTA))
    cli.main(["--home", str(target), "doctor", "--smoke", "--only", "gemini"])
    out = capsys.readouterr()
    assert "resting" in out.out and "not saved" in (out.out + out.err)


def test_ctrl_c_stops_cleanly_with_what_was_printed(home, monkeypatch, capsys):
    def interrupt(prompt):
        raise KeyboardInterrupt

    monkeypatch.setattr(ask, "ADAPTERS", {**adapters(), "grok": interrupt})
    assert cli.main(["--home", str(home), "doctor", "--smoke", "--only", "grok"]) == 130
    assert "stopped" in capsys.readouterr().err.lower()


def test_kaizen_routing_waste_ignores_smoke_records():
    from lifeos import kaizen
    rows = [{"command": "smoke", "model": "gemini", "status": "failed"}]
    waste = kaizen._routing_waste(rows, [])
    assert "gemini" not in str(waste)
