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
    assert names == {"lifeos_task_list", "lifeos_task_new", "lifeos_context", "lifeos_result_write", "lifeos_ask", "lifeos_delegate"}


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
    assert err and "class C" in text
    assert path.read_text(encoding="utf-8") == before


def test_ask_tool_uses_the_adapters(home, monkeypatch):
    monkeypatch.setitem(ask.ADAPTERS, "codex", lambda prompt: "FROM CODEX")
    text, err = tool(home, "lifeos_ask", model="codex", task="T-261116")
    assert not err and "FROM CODEX" in (home / "tasks" / "T-261116-demo-cli.md").read_text(encoding="utf-8")


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
