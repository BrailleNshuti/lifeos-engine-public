import io
import json
import shutil

import pytest

from lifeos import ask, mcp
from lifeos.cli import main


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def call(home, method, params=None, id=1):
    return mcp.handle(home, {"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}})


def tool(home, name, **arguments):
    reply = call(home, "tools/call", {"name": name, "arguments": arguments})
    return reply["result"]["content"][0]["text"], reply["result"].get("isError", False)


def test_initialize_and_tool_list(home):
    reply = call(home, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
    assert reply["result"]["protocolVersion"] == "2025-06-18"
    assert "tools" in reply["result"]["capabilities"] and reply["result"]["serverInfo"]["name"] == "lifeos"
    names = {t["name"] for t in call(home, "tools/list")["result"]["tools"]}
    assert names == {"lifeos_task_list", "lifeos_task_new", "lifeos_context", "lifeos_result_write",
                     "lifeos_ask", "lifeos_delegate", "lifeos_review"}



def test_notifications_get_no_reply(home):
    assert mcp.handle(home, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_task_list_and_context(home):
    text, err = tool(home, "lifeos_task_list")
    assert not err and "T-261116-demo-cli" in text
    text, err = tool(home, "lifeos_context", task="T-261116")
    assert not err and "=== rules.md" in text and "=== tasks/T-261116-demo-cli.md" in text


def test_task_new_creates_a_file(home):
    text, err = tool(home, "lifeos_task_new", sentence="Plan the landing page")
    assert not err and "plan-landing-page" in text
    assert list((home / "tasks").glob("*plan-landing-page*.md"))


def test_result_write_appends_and_logs(home):
    before = (home / "tasks" / "T-261116-demo-cli.md").read_text(encoding="utf-8")
    text, err = tool(home, "lifeos_result_write", task="T-261116", model="claude-chat", text="Plan: A, B, C.")
    assert not err
    after = (home / "tasks" / "T-261116-demo-cli.md").read_text(encoding="utf-8")
    assert after.startswith(before) and "## Result · claude-chat ·" in after and "Plan: A, B, C." in after
    assert "claude-chat" in (home / "logs" / "ledger.csv").read_text(encoding="utf-8").splitlines()[-1]


def test_result_write_is_stopped_by_the_guard(home):
    path = home / "tasks" / "T-261116-demo-cli.md"
    before = path.read_text(encoding="utf-8")
    text, err = tool(home, "lifeos_result_write", task="T-261116", model="x", text="key " + "ghp_" + "a1" * 18)
    assert err and "sensitive finding" in text
    assert path.read_text(encoding="utf-8") == before


def test_ask_tool_uses_the_adapters(home, monkeypatch):
    monkeypatch.setitem(ask.ADAPTERS, "codex", lambda prompt: "FROM CODEX")
    text, err = tool(home, "lifeos_ask", model="codex", task="T-261116")
    assert not err and "FROM CODEX" in (home / "tasks" / "T-261116-demo-cli.md").read_text(encoding="utf-8")


def test_review_and_context_explain_tools(home, monkeypatch):
    monkeypatch.setitem(ask.ADAPTERS, "codex", lambda prompt: "Checked a.py. Next step: ok.")
    monkeypatch.setitem(ask.ADAPTERS, "claude", lambda prompt: "Checked b.py. Next step: ok.")
    text, err = tool(home, "lifeos_review", task="T-261116", reviewers="codex,claude")
    assert not err and "review:codex" in text and "review:claude" in text
    exp, err = tool(home, "lifeos_context", task="T-261116", explain=True)
    assert not err and "sha256" in exp



@pytest.mark.parametrize("bad", ["../now", "..\\now", "T-1/../../x", "*", "T-261116*/../..", ""])
def test_task_ids_cannot_leave_the_tasks_folder(home, bad):
    for name, args in [("lifeos_context", {"task": bad}),
                       ("lifeos_result_write", {"task": bad, "model": "m", "text": "t"})]:
        text, err = tool(home, name, **args)
        assert err


def test_errors_are_results_not_crashes(home):
    text, err = tool(home, "lifeos_context", task="T-999999")
    assert err and "not found" in text
    assert "error" in call(home, "tools/call", {"name": "nope", "arguments": {}})
    assert call(home, "no/such/method")["error"]["code"] == -32601


def test_serve_speaks_json_lines(home):
    lines = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
             {"jsonrpc": "2.0", "method": "notifications/initialized"},
             {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    out = io.StringIO()
    mcp.serve(home, io.StringIO("\n".join(json.dumps(m) for m in lines) + "\nnot json\n"), out)
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [r.get("id") for r in replies] == [1, 2, None]  # last one: parse error, still valid JSON
    assert replies[2]["error"]["code"] == -32700


def test_cli_wiring(home, monkeypatch):
    monkeypatch.setattr(mcp, "serve", lambda h, i, o: print("served", h.name))
    assert main(["--home", str(home), "mcp"]) == 0


def test_cli_tools_never_inherit_the_mcp_input_stream(monkeypatch):
    """agy reads stdin when it is inherited; inside `lifeos mcp` that stream is the chat connection."""
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw)
        return type("R", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

    monkeypatch.setattr(ask.subprocess, "run", fake_run)
    monkeypatch.setattr(ask.shutil, "which", lambda c: c)
    ask._run_cli(["agy", "-p", "x"], "x", via_stdin=False)
    assert seen["stdin"] is ask.subprocess.DEVNULL


def test_an_unexpected_error_in_a_tool_does_not_kill_the_server(home, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(ask, "run_ask", boom)
    reply = mcp.handle(home, {"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                              "params": {"name": "lifeos_ask", "arguments": {"task": "T-261116", "model": "codex"}}})
    assert reply["result"]["isError"] and "unexpected" in reply["result"]["content"][0]["text"]


def test_task_new_refuses_class_c_text_and_creates_no_file(home):
    iban = "DE89 3704 " + "0044 0532 0130 00"
    before = sorted(p.name for p in (home / "tasks").iterdir())
    text, err = tool(home, "lifeos_task_new", sentence=f"Pay rent to {iban}")
    assert err and "IBAN" in text
    assert sorted(p.name for p in (home / "tasks").iterdir()) == before


def test_json_that_is_not_an_object_gets_an_error_reply(home):
    for bad in ([1, 2], 5, "text", None):
        reply = mcp.handle(home, bad)
        assert reply["error"]["code"] == -32600


def test_a_model_name_cannot_inject_ledger_rows(home):
    ledger = home / "logs" / "ledger.csv"
    before = len(ledger.read_text(encoding="utf-8").splitlines())
    tool(home, "lifeos_result_write", task="T-261116", model="x\n2026-11-20,T-1,claude,999,injected", text="Plan: A.")
    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert len(lines) == before + 1 and "999" not in lines[-1].split(",")[3:4]
    task = (home / "tasks" / "T-261116-demo-cli.md").read_text(encoding="utf-8")
    assert "\n2026-11-20,T-1" not in task


def test_odd_shapes_of_params_and_tool_name_get_an_error_not_a_crash(home):
    for params in ([1], "x", {"name": ["lifeos_task_list"]}, {"name": {"a": 1}}):
        reply = call(home, "tools/call", params)
        assert reply["error"]["code"] == -32602


def test_mcp_entrypoint_prevents_home_lifeos_folder_shadowing(tmp_path, demo):
    """When an MCP client spawns from ~ and ~/lifeos exists as the data repo, `lifeos mcp` (and `python -P`
    on Python 3.11+) must not treat ~/lifeos as a PEP 420 namespace package shadowing `lifeos`."""
    import os
    import subprocess
    import sys

    data_repo = tmp_path / "lifeos"
    shutil.copytree(demo, data_repo)
    env = {**os.environ, "LIFEOS_HOME": str(data_repo), "PYTHONSAFEPATH": "1"}
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n"
    exe = shutil.which("lifeos")
    cmd = [exe, "mcp"] if exe else [sys.executable, *(["-P"] if sys.version_info >= (3, 11) else []), "-m", "lifeos.cli", "mcp"]
    proc = subprocess.run(
        cmd, input=req, capture_output=True, text=True, encoding="utf-8", cwd=tmp_path, env=env, timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip()) == {"jsonrpc": "2.0", "id": 1, "result": {}}




