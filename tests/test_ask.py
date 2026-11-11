import datetime as dt
import shutil

import pytest

from lifeos import ask
from lifeos.cli import main

TODAY = dt.date(2026, 11, 20)


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def fake(prompt):
    fake.prompts.append(prompt)
    return "FAKE ANSWER"


fake.prompts = []


def test_ask_appends_result_and_ledger(home):
    fake.prompts.clear()
    original = (home / "tasks" / "T-261116-demo-cli.md").read_text(encoding="utf-8")
    path = ask.run_ask(home, "fake", "T-261116", adapters={"fake": fake}, today=TODAY)
    text = path.read_text(encoding="utf-8")
    assert "## Result · fake · 2026-11-20\nFAKE ANSWER" in text
    assert text.startswith(original) and text.endswith("FAKE ANSWER\n")  # appended, nothing rewritten
    ledger = (home / "logs" / "ledger.csv").read_text(encoding="utf-8").splitlines()
    assert ledger[-1].startswith("2026-11-20,T-261116-demo-cli,fake,")
    assert "=== rules.md" in fake.prompts[0] and "T-261116-demo-cli" in fake.prompts[0]


def test_ledger_line_keeps_the_weekly_numbers_working(home):
    ask.run_ask(home, "fake", "T-261116", adapters={"fake": fake}, today=TODAY)
    assert main(["--home", str(home), "week", "--week", "2026-W47"]) == 0


def test_dry_run_calls_nothing_and_writes_nothing(home):
    def boom(prompt):
        raise AssertionError("adapter must not run")

    before = (home / "tasks" / "T-261116-demo-cli.md").read_text(encoding="utf-8")
    ledger_before = (home / "logs" / "ledger.csv").read_text(encoding="utf-8")
    pack, tokens = ask.run_ask(home, "fake", "T-261116", dry_run=True, adapters={"fake": boom}, today=TODAY)
    assert "=== rules.md" in pack and tokens > 0
    assert (home / "tasks" / "T-261116-demo-cli.md").read_text(encoding="utf-8") == before
    assert (home / "logs" / "ledger.csv").read_text(encoding="utf-8") == ledger_before


def test_guard_block_stops_the_call(home):
    task = home / "tasks" / "T-261116-demo-cli.md"
    task.write_text(task.read_text(encoding="utf-8") + "\ntoken " + "ghp_" + "a1" * 18 + "\n", encoding="utf-8")

    def boom(prompt):
        raise AssertionError("must not be called")

    with pytest.raises(ask.Blocked):
        ask.run_ask(home, "fake", "T-261116", adapters={"fake": boom}, today=TODAY)
    assert main(["--home", str(home), "ask", "codex", "T-261116"]) == 1


def test_unknown_model_and_unknown_task(home):
    with pytest.raises(ValueError):
        ask.run_ask(home, "nope", "T-261116", adapters={"fake": fake}, today=TODAY)
    with pytest.raises(FileNotFoundError):
        ask.run_ask(home, "fake", "T-999999", adapters={"fake": fake}, today=TODAY)


def test_missing_tool_exits_2(home, monkeypatch, capsys):
    monkeypatch.setenv("PATH", "")
    assert main(["--home", str(home), "ask", "codex", "T-261116"]) == 2
    assert "codex" in capsys.readouterr().err


def test_cli_adapters_use_stdin_and_current_flags(monkeypatch):
    calls = []

    class Done:
        returncode, stdout, stderr = 0, "OUT\n", ""

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        return Done()

    monkeypatch.setattr(ask.subprocess, "run", fake_run)
    assert ask.ask_codex("P") == "OUT"
    assert ask.ask_gemini("P") == "OUT"
    assert ask.ask_claude("P") == "OUT"
    assert calls[0][0] == ["codex", "exec", "-"]
    assert calls[1][0][:2] == ["gemini", "-p"]
    assert calls[2][0] == ["claude", "-p", "--model", "sonnet"]
    assert all(kw["input"] == "P" for _, kw in calls)


def test_cli_adapter_failure_is_reported(monkeypatch):
    class Bad:
        returncode, stdout, stderr = 1, "", "boom"

    monkeypatch.setattr(ask.subprocess, "run", lambda *a, **k: Bad())
    with pytest.raises(ask.AskError):
        ask.ask_codex("P")


def test_ollama_adapter_uses_local_address(monkeypatch):
    seen = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"response": "LOCAL"}'

    def fake_open(req, timeout):
        seen["url"], seen["body"] = req.full_url, req.data
        return Resp()

    monkeypatch.setattr(ask.urllib.request, "urlopen", fake_open)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    assert ask.ask_ollama("P") == "LOCAL"
    assert seen["url"] == "http://localhost:11434/api/generate" and b'"stream": false' in seen["body"]


def test_class_c_data_in_the_answer_is_not_written(home):
    leaky = lambda prompt: "key " + "ghp_" + "a1" * 18  # noqa: E731
    before = (home / "tasks" / "T-261116-demo-cli.md").read_text(encoding="utf-8")
    with pytest.raises(ask.Blocked):
        ask.run_ask(home, "fake", "T-261116", adapters={"fake": leaky}, today=TODAY)
    assert (home / "tasks" / "T-261116-demo-cli.md").read_text(encoding="utf-8") == before
