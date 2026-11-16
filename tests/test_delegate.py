import json
import shutil
import urllib.error

import pytest

from lifeos import ask, delegate, mcp, seats
from lifeos.cli import main


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def answer(name):
    def fn(prompt):
        return f"ANSWER FROM {name}"
    return fn


ADAPTERS = {m: answer(m) for m in ("claude", "codex", "gemini", "ollama", "qwen")}


@pytest.mark.parametrize("text,model", [
    ("Fix the failing pytest in the parser", "codex"),
    ("Summarise this long document and read all 40 pages", "gemini"),
    ("Sort my private finance csv into categories", "qwen"),
    ("Draft the plan and decide what to cut", "claude"),
    ("Quiz me on German exam vocabulary", "codex"),
    ("Something with no clear keyword", "claude"),
    ("What is the latest price of the laptop", "gemini"),  # live facts: Grok is not wired yet, Gemini searches
])
def test_pick_routes_by_kind_of_work(text, model):
    assert delegate.pick(text)[0] == model


def test_pick_matches_whole_words_only():
    assert delegate.pick("the latest build")[0] != "codex"  # 'test' inside 'latest' is not a test task


def test_pick_gives_a_reason():
    assert delegate.pick("refactor the module")[1]


def test_private_beats_code():
    assert delegate.pick("sort my private csv with a python script")[0] == "qwen"


def test_delegate_runs_the_picked_model_and_returns_its_text(home):
    out = delegate.run_delegate(home, "T-261116", adapters=ADAPTERS)  # demo task is about the CLI
    assert out["model"] == "codex" and out["text"] == "ANSWER FROM codex" and out["tried"] == ["codex"]
    assert "ANSWER FROM codex" in out["path"].read_text(encoding="utf-8")


def test_explicit_model_wins(home):
    out = delegate.run_delegate(home, "T-261116", model="gemini", adapters=ADAPTERS)
    assert out["model"] == "gemini" and "chosen by you" in out["reason"]


def test_missing_tool_falls_back_and_says_so(home):
    def gone(prompt):
        raise ask.ToolMissing("codex is not installed")

    out = delegate.run_delegate(home, "T-261116", adapters={**ADAPTERS, "codex": gone})
    assert out["model"] == "claude" and out["tried"] == ["codex", "claude"]
    assert "fell back" in out["reason"]


def test_all_failing_raises_the_last_error(home):
    def gone(prompt):
        raise ask.ToolMissing("nope")

    with pytest.raises(ask.ToolMissing):
        delegate.run_delegate(home, "T-261116", adapters={m: gone for m in ADAPTERS})


def test_a_failed_call_is_replaced_and_the_reason_is_written(home):
    def broken(prompt):
        raise ask.AskError("codex failed: You've hit your usage limit. try again at Nov 18th, 2026 4:02 PM")

    out = delegate.run_delegate(home, "T-261116", adapters={**ADAPTERS, "codex": broken})
    assert out["model"] == "claude" and out["tried"] == ["codex", "claude"]
    assert "usage_limit" in out["reason"] and "fell back" in out["reason"]
    text = out["path"].read_text(encoding="utf-8")
    note = text.split("## Route", 1)[1]
    assert "usage_limit" in note and "R-" in note
    assert "Route" not in out["text"] and out["text"] == "ANSWER FROM claude"


def test_unknown_model_is_an_error(home):
    with pytest.raises(ValueError):
        delegate.run_delegate(home, "T-261116", model="nope", adapters=ADAPTERS)


def test_guard_still_blocks_before_anything_is_sent(home):
    task = home / "tasks" / "T-261116-demo-cli.md"
    task.write_text(task.read_text(encoding="utf-8") + "\ntoken " + "ghp_" + "a1" * 18 + "\n", encoding="utf-8")

    def boom(prompt):
        raise AssertionError("must not run")

    with pytest.raises(ask.Blocked):
        delegate.run_delegate(home, "T-261116", adapters={m: boom for m in ADAPTERS})


def test_last_result_returns_only_the_newest_section(tmp_path):
    f = tmp_path / "t.md"
    f.write_text("## Task\nx\n\n## Result · a · 2026-11-11\nfirst\n\n## Result · b · 2026-11-12\nsecond\nline\n", encoding="utf-8")
    assert delegate.last_result(f) == "second\nline"


def test_cli_delegate_prints_model_and_answer(home, monkeypatch, capsys):
    monkeypatch.setattr(ask, "ADAPTERS", ADAPTERS)
    monkeypatch.setattr(delegate, "ADAPTERS", ADAPTERS)
    assert main(["--home", str(home), "delegate", "T-261116"]) == 0
    out = capsys.readouterr().out
    assert "codex" in out and "ANSWER FROM codex" in out


def test_cli_delegate_dry_run_sends_nothing(home, monkeypatch, capsys):
    def boom(prompt):
        raise AssertionError("must not run")

    monkeypatch.setattr(delegate, "ADAPTERS", {m: boom for m in ADAPTERS})
    assert main(["--home", str(home), "delegate", "T-261116", "--dry-run"]) == 0
    assert "codex" in capsys.readouterr().out


def test_cli_delegate_shows_the_check_line_when_the_answer_is_empty(home, monkeypatch, capsys):
    """An empty answer is the case CHECK exists for. The MCP tool shows it; the command line must not stay silent."""
    silent = {m: (lambda prompt: "") for m in ADAPTERS}
    monkeypatch.setattr(ask, "ADAPTERS", silent)
    monkeypatch.setattr(delegate, "ADAPTERS", silent)
    assert main(["--home", str(home), "delegate", "T-261116"]) == 0
    assert "CHECK (free, no model): empty answer" in capsys.readouterr().out


def test_mcp_has_a_delegate_tool_and_boss_instructions(home):
    init = mcp.handle(home, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})["result"]
    assert "lifeos_delegate" in init["instructions"] and "decision" in init["instructions"]
    names = {t[0] for t in mcp.TOOLS}
    assert "lifeos_delegate" in names


def test_mcp_delegate_returns_the_answer_to_the_chat(home, monkeypatch):
    monkeypatch.setattr(delegate, "ADAPTERS", ADAPTERS)
    reply = mcp.handle(home, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                              "params": {"name": "lifeos_delegate", "arguments": {"task": "T-261116"}}})
    text = reply["result"]["content"][0]["text"]
    assert not reply["result"]["isError"] and "codex" in text and "ANSWER FROM codex" in text


# --- qwen and the shared Ollama adapter ---

def _fake_ollama(monkeypatch, payload=None, error=None):
    seen = {}

    class Resp:
        def read(self):
            return json.dumps({"response": payload}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        seen["model"] = json.loads(req.data)["model"]
        if error:
            raise error
        return Resp()

    monkeypatch.setattr(ask, "_open_local", fake_urlopen)  # the adapter bypasses the proxy through _open_local
    return seen


def test_qwen_is_an_adapter_and_uses_its_own_model(monkeypatch):
    monkeypatch.setenv("LIFEOS_QWEN_MODEL", "qwen3:4b")
    seen = _fake_ollama(monkeypatch, "hello")
    assert "qwen" in ask.ADAPTERS and ask.ask_qwen("hi") == "hello" and seen["model"] == "qwen3:4b"
    assert ask.label("qwen") == "qwen:qwen3:4b"


def test_thinking_blocks_are_removed(monkeypatch):
    _fake_ollama(monkeypatch, "<think>long reasoning\nmore</think>\nFinal answer")
    assert ask.ask_qwen("hi") == "Final answer"


def test_unpulled_model_says_how_to_pull_it(monkeypatch):
    _fake_ollama(monkeypatch, error=urllib.error.HTTPError("u", 404, "not found", {}, None))
    with pytest.raises(ask.ToolMissing, match="ollama pull"):
        ask.ask_qwen("hi")


def test_a_private_failure_never_reaches_the_cloud(home):
    """A failed local seat stops. It is not replaced by Claude, Codex or Gemini."""
    cloud = []

    def down(prompt):
        raise ask.AskError("qwen timed out")

    adapters = {**ADAPTERS, "qwen": down, "ollama": down, "claude": lambda prompt: cloud.append(prompt) or "cloud"}
    with pytest.raises(ask.AskError):
        delegate.run_delegate(home, "T-261116", model="qwen", adapters=adapters)
    assert cloud == []
    note = (home / "tasks" / "T-261116-demo-cli.md").read_text(encoding="utf-8").split("## Route", 1)[1]
    assert "claude" not in note.lower() and "timeout" in note


def test_route_notes_are_not_sent_again(home):
    task = home / "tasks" / "T-261116-demo-cli.md"
    task.write_text(task.read_text(encoding="utf-8") + "\n## Route · 2026-11-16\n- codex usage_limit: rested\n", encoding="utf-8")
    seen = {}

    def grab(prompt):
        seen["prompt"] = prompt
        return "ANSWER FROM codex with a next step"

    delegate.run_delegate(home, "T-261116", adapters={**ADAPTERS, "codex": grab})
    assert "usage_limit" not in seen["prompt"] and "Route" not in seen["prompt"]


def test_a_resting_seat_is_skipped_before_the_call(home, monkeypatch):
    monkeypatch.setattr(seats, "pressure", lambda records, now: {"codex": "usage limit until 2026-11-18 16:02 UTC"})
    out = delegate.run_delegate(home, "T-261116", adapters=ADAPTERS)
    assert out["model"] == "claude" and out["tried"] == ["claude"]
    assert "skipped codex" in out["reason"]


def test_a_private_task_never_falls_back_to_the_cloud(home):
    """Private sorting stays on this laptop: if the local model is down, stop instead of asking cloud Claude."""
    def down(prompt):
        raise ask.ToolMissing("ollama is not running")

    cloud = []
    adapters = {**ADAPTERS, "qwen": down, "ollama": down, "claude": lambda prompt: cloud.append(prompt) or "cloud"}
    for model in ("qwen", "ollama"):
        with pytest.raises(ask.ToolMissing):
            delegate.run_delegate(home, "T-261116", model=model, adapters=adapters)
    assert cloud == []
