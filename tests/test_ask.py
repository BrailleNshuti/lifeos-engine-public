import csv
import datetime as dt
import shutil

import pytest

from lifeos import ask
from lifeos.cli import main
from lifeos.week import week_numbers

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
    monkeypatch.setattr(ask.shutil, "which", lambda name: name)
    assert ask.ask_codex("P") == "OUT"
    assert ask.ask_gemini("P") == "OUT"
    assert ask.ask_claude("P") == "OUT"
    assert calls[0][0] == ["codex", "exec", "--skip-git-repo-check", "-s", "read-only", "-"]
    assert calls[1][0] == ["agy", "--sandbox", "-p", "P"] and calls[1][1]["input"] is None
    claude_cmd = calls[2][0]
    assert claude_cmd == [
        "claude", "-p", "--model", "sonnet",
        "--safe-mode", "--restricted", "--tools", "Read,Glob,Grep",
        "--strict-mcp-config", "--no-session-persistence",
        "--permission-prompts", "none",
    ]
    assert not any(tool in claude_cmd for tool in ("Bash", "PowerShell", "Edit", "Write", "WebFetch"))
    assert all(kw["cwd"] for _, kw in calls)  # runs in an empty temp folder
    assert calls[0][1]["input"] == "P" and calls[2][1]["input"] == "P"


def test_cli_adapter_failure_is_reported_and_redacted(monkeypatch):
    sentinel = "ghp_" + "b2" * 18
    synth_email = "jane" + "@" + "example.org"

    class Bad:
        returncode, stdout, stderr = 1, "", f"boom {sentinel} email {synth_email}"

    monkeypatch.setattr(ask.subprocess, "run", lambda *a, **k: Bad())
    monkeypatch.setattr(ask.shutil, "which", lambda name: name)
    with pytest.raises(ask.AskError) as exc_info:
        ask.ask_codex("P")
    assert sentinel not in str(exc_info.value)
    assert synth_email not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)


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

    monkeypatch.setattr(ask, "_open_local", fake_open)  # the adapter bypasses the proxy through _open_local
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    assert ask.ask_ollama("P") == "LOCAL"
    assert seen["url"] == "http://localhost:11434/api/generate" and b'"stream": false' in seen["body"]


def test_class_c_data_in_the_answer_is_not_written(home):
    leaky = lambda prompt: "key " + "ghp_" + "a1" * 18  # noqa: E731
    before = (home / "tasks" / "T-261116-demo-cli.md").read_text(encoding="utf-8")
    with pytest.raises(ask.Blocked):
        ask.run_ask(home, "fake", "T-261116", adapters={"fake": leaky}, today=TODAY)
    assert (home / "tasks" / "T-261116-demo-cli.md").read_text(encoding="utf-8") == before


def test_windows_cmd_shim_is_found_and_run(monkeypatch):
    seen = []

    class Done:
        returncode, stdout, stderr = 0, "OK", ""

    monkeypatch.setattr(ask.shutil, "which", lambda name: r"C:\npm\codex.cmd")
    monkeypatch.setattr(ask.subprocess, "run", lambda cmd, **kw: seen.append(cmd) or Done())
    assert ask.ask_codex("P") == "OK" and seen[0][:2] == [r"C:\npm\codex.cmd", "exec"]


def test_small_budget_keeps_the_task_in_ask(home):
    fake.prompts.clear()
    ask.run_ask(home, "fake", "T-261116", budget=300, adapters={"fake": fake}, today=TODAY)
    assert "=== tasks/T-261116-demo-cli.md" in fake.prompts[0]


def test_ambiguous_task_prefix_is_an_error(home):
    (home / "tasks" / "T-261116-demo-cli-2.md").write_text("---\nid: x\n---\n", encoding="utf-8")
    with pytest.raises(ValueError):
        ask.run_ask(home, "fake", "T-261116-demo", adapters={"fake": fake}, today=TODAY)
    ask.run_ask(home, "fake", "T-261116-demo-cli", adapters={"fake": fake}, today=TODAY)  # exact id still works


def test_personal_files_only_go_out_with_full(home):
    fake.prompts.clear()
    ask.run_ask(home, "fake", "T-261116", adapters={"fake": fake}, today=TODAY)
    ask.run_ask(home, "fake", "T-261116", adapters={"fake": fake}, today=TODAY, full=True)
    assert "=== now.md" not in fake.prompts[0] and "=== me.md" not in fake.prompts[0]
    assert "=== now.md" in fake.prompts[1] and "=== me.md" in fake.prompts[1]


def test_agy_refuses_a_prompt_too_long_for_a_command_line():
    with pytest.raises(ask.AskError):
        ask.ask_gemini("x" * 40000)


def test_ollama_result_names_the_local_model(home, monkeypatch):
    monkeypatch.setenv("LIFEOS_OLLAMA_MODEL", "deepseek-r1:1.5b")
    path = ask.run_ask(home, "ollama", "T-261116", adapters={"ollama": fake}, today=TODAY)
    assert "## Result · ollama:deepseek-r1:1.5b · 2026-11-20" in path.read_text(encoding="utf-8")


HEDGY = "All done, it works. I think it should work, probably; next step: none."  # 2 flags, one flag text has a comma
CLEAN = "Added the check in lifeos/ask.py and tests/test_ask.py. Next step: review the diff."  # 0 flags


def last_ledger_row(home):
    with open(home / "logs" / "ledger.csv", newline="", encoding="utf-8") as f:
        return list(csv.reader(f))[-1]


def test_ledger_note_holds_the_number_of_flags(home):
    ask.run_ask(home, "fake", "T-261116", adapters={"fake": lambda prompt: HEDGY}, today=TODAY)
    assert last_ledger_row(home) == ["2026-11-20", "T-261116-demo-cli", "fake", "", "asked via lifeos ask; flags: 2"]


def test_a_clean_answer_is_written_as_flags_zero(home):
    ask.run_ask(home, "fake", "T-261116", adapters={"fake": lambda prompt: CLEAN}, today=TODAY)
    assert last_ledger_row(home)[4] == "asked via lifeos ask; flags: 0"


def test_ledger_never_holds_the_answer_or_the_flag_texts(home):
    ask.run_ask(home, "fake", "T-261116", adapters={"fake": lambda prompt: HEDGY}, today=TODAY)
    ledger = (home / "logs" / "ledger.csv").read_text(encoding="utf-8")
    assert ledger.splitlines()[0] == "date,task,model,minutes_saved,note"  # columns unchanged
    assert "probably" not in ledger and "guesses" not in ledger and "without evidence" not in ledger
    assert len(last_ledger_row(home)) == 5  # the comma inside a flag text never became a column


def test_commas_in_a_ledger_note_are_valid_csv(home):
    ask.write_result(home, "T-261116", "chat", CLEAN, today=TODAY, note="written, then checked, by hand")
    assert last_ledger_row(home) == ["2026-11-20", "T-261116-demo-cli", "chat", "", "written, then checked, by hand"]


def test_ollama_refuses_a_remote_host_before_sending(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "https://models.example.com")
    monkeypatch.setattr(ask, "_open_local", lambda *args: pytest.fail("request must not be opened"))
    with pytest.raises(ask.Blocked, match="may only use Ollama on this computer"):
        ask.ask_qwen("private task text")


def test_ledger_without_a_final_newline_keeps_its_rows_apart(home):
    """Editors often save logs/ledger.csv without a last newline; the new row must not be glued to the old one."""
    ledger = home / "logs" / "ledger.csv"
    rows = ledger.read_text(encoding="utf-8").splitlines()
    ledger.write_text("\n".join(rows), encoding="utf-8")  # the same rows, no newline at the end
    ask.run_ask(home, "fake", "T-261116", adapters={"fake": fake}, today=TODAY)
    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert lines[:-1] == rows and lines[-1].startswith("2026-11-20,T-261116-demo-cli,fake,")
    assert week_numbers(home, "2026-W47")["ledger_lines"] == 4  # the 3 rows already in that week plus the new one


def test_local_ollama_request_ignores_the_system_proxy(monkeypatch):
    """With http_proxy set, the 'local' request (prompt text included) must not be sent to the proxy."""
    import http.server
    import json as _json
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            body = _json.dumps({"response": "local answer"}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("OLLAMA_HOST", f"127.0.0.1:{server.server_port}")
        for name in ("http_proxy", "HTTP_PROXY"):
            monkeypatch.setenv(name, "http://127.0.0.1:9")  # nothing listens there: a proxied request fails
        monkeypatch.delenv("no_proxy", raising=False)
        monkeypatch.delenv("NO_PROXY", raising=False)
        assert ask.ask_ollama("hello") == "local answer"
    finally:
        server.shutdown()


def test_an_ollama_timeout_is_not_reported_as_a_missing_tool(monkeypatch):
    import urllib.request

    def slow(self, *args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", slow)
    with pytest.raises(ask.AskError, match="did not answer") as caught:
        ask.ask_ollama("hello")
    assert not isinstance(caught.value, ask.ToolMissing)


def test_run_ask_writes_immutable_run_record_in_runs_jsonl(home):
    import json as _json

    ask.run_ask(home, "fake", "T-261116", adapters={"fake": lambda prompt: CLEAN}, today=TODAY)
    runs = (home / "logs" / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    rec = _json.loads(runs[-1])
    assert rec["run_id"].startswith("R-261120-")
    assert rec["command"] == "ask" and rec["task_id"] == "T-261116-demo-cli" and rec["flags"] == 0
    assert len(rec["context_sha256"]) == 64


def test_blind_multi_model_review_hides_earlier_answers_and_logs_parent_run(home):
    import json as _json

    seen = {}

    def rev_codex(prompt):
        seen["codex"] = prompt
        return "Checked lifeos/store.py: 0 bugs found. Next step: merge."

    def rev_gemini(prompt):
        seen["gemini"] = prompt
        return "Checked tests/test_store.py: edge cases covered. Next step: ship."

    # First model writes an answer; neither blind reviewer may see it!
    ask.write_result(home, "T-261116", "claude", "FIRST MODEL SECRET VERDICT", today=TODAY)
    out = ask.run_review(home, "T-261116", reviewers=("codex", "gemini"),
                         adapters={"codex": rev_codex, "gemini": rev_gemini}, today=TODAY)
    assert "FIRST MODEL SECRET VERDICT" not in seen["codex"]
    assert "FIRST MODEL SECRET VERDICT" not in seen["gemini"]
    assert "0 bugs found" not in seen["gemini"]  # Reviewer 2 never sees Reviewer 1's answer
    text = (home / "tasks" / "T-261116-demo-cli.md").read_text(encoding="utf-8")
    assert "## Result · review:codex · 2026-11-20" in text
    assert "## Result · review:gemini · 2026-11-20" in text
    runs = [_json.loads(line) for line in (home / "logs" / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["parent_run_id"] for r in runs[-3:-1]] == [out["group_run_id"], out["group_run_id"]]
    assert runs[-1]["run_id"] == out["group_run_id"] and runs[-1]["command"] == "review_group"


