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
    assert names == {
        "lifeos_task_list", "lifeos_task_new", "lifeos_context", "lifeos_result_write",
        "lifeos_ask", "lifeos_delegate", "lifeos_review",
        "lifeos_week", "lifeos_log", "lifeos_runs", "lifeos_kaizen",
        "lifeos_route", "lifeos_cockpit",
        "lifeos_exam", "lifeos_bakeoff", "lifeos_showcase",
    }



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
    sentinel = "ghp_" + "c3" * 18

    def boom(*a, **k):
        raise RuntimeError(f"unexpected {sentinel}")

    monkeypatch.setattr(ask, "run_ask", boom)
    reply = mcp.handle(home, {"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                              "params": {"name": "lifeos_ask", "arguments": {"task": "T-261116", "model": "codex"}}})
    msg = reply["result"]["content"][0]["text"]
    assert reply["result"]["isError"] and "unexpected" in msg
    assert sentinel not in msg and "[REDACTED]" in msg


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


def test_mcp_ask_and_review_run_id_idempotency_retry_mismatch_and_concurrency(home, monkeypatch):
    import threading
    import time

    tools_by_name = {t["name"]: t["inputSchema"] for t in call(home, "tools/list")["result"]["tools"]}
    assert "run_id" in tools_by_name["lifeos_ask"]["properties"]
    assert "run_id" in tools_by_name["lifeos_review"]["properties"]
    assert "run_id" not in tools_by_name["lifeos_delegate"]["properties"]

    # 1. Invalid run_id shapes rejected with isError=True
    for bad_rid in ("", "../escape", "bad space", 123):
        txt, is_err = tool(home, "lifeos_ask", model="codex", task="T-261116", run_id=bad_rid)
        assert is_err and "run_id" in txt

    # 2. Successful ask + lost-response retry -> 1 provider invocation, 1 terminal record, run_id in output
    ask_calls = []

    def codex_ok(prompt):
        ask_calls.append(prompt)
        return "Checked ask idempotency in lifeos/mcp.py. Next step: verify retry."

    monkeypatch.setitem(ask.ADAPTERS, "codex", codex_ok)
    rid_ok = "R-261120-mcpask01"
    out1, err1 = tool(home, "lifeos_ask", model="codex", task="T-261116", run_id=rid_ok)
    out2, err2 = tool(home, "lifeos_ask", model="codex", task="T-261116", run_id=rid_ok)
    assert not err1 and not err2
    assert rid_ok in out1 and rid_ok in out2
    assert len(ask_calls) == 1
    task_body = (home / "tasks" / "T-261116-demo-cli.md").read_text(encoding="utf-8")
    assert task_body.count("Checked ask idempotency in lifeos/mcp.py.") == 1

    # 3. Mismatched request identity on same run_id -> isError=True, no extra provider call
    for mismatch_kwargs in (
        {"model": "claude", "task": "T-261116", "run_id": rid_ok},
        {"model": "codex", "task": "T-261116", "budget": 4000, "run_id": rid_ok},
        {"model": "codex", "task": "T-261116", "full": True, "run_id": rid_ok},
    ):
        m_txt, m_err = tool(home, "lifeos_ask", **mismatch_kwargs)
        assert m_err and rid_ok in m_txt
    assert len(ask_calls) == 1

    # 4. Persisted failed execution replay -> isError=True without calling provider again
    fail_calls = []

    def codex_fail(prompt):
        fail_calls.append(prompt)
        raise ask.AskError("codex failed: upstream error")

    monkeypatch.setitem(ask.ADAPTERS, "codex", codex_fail)
    rid_fail = "R-261120-mcpfail1"
    f1, ferr1 = tool(home, "lifeos_ask", model="codex", task="T-261116", run_id=rid_fail)
    f2, ferr2 = tool(home, "lifeos_ask", model="codex", task="T-261116", run_id=rid_fail)
    assert ferr1 and ferr2
    assert "upstream error" in f1 and "upstream error" in f2
    assert len(fail_calls) == 1

    # 5. Successful review + lost-response retry + mismatched identity
    rev_calls = []

    def rev_codex(prompt):
        rev_calls.append(("codex", prompt))
        return "Reviewed lifeos/mcp.py. Next step: none."

    def rev_claude(prompt):
        rev_calls.append(("claude", prompt))
        return "Reviewed tests/test_mcp.py. Next step: none."

    monkeypatch.setitem(ask.ADAPTERS, "codex", rev_codex)
    monkeypatch.setitem(ask.ADAPTERS, "claude", rev_claude)
    rid_rev = "R-261120-mcprev01"
    r1, rerr1 = tool(home, "lifeos_review", task="T-261116", reviewers="codex,claude", run_id=rid_rev)
    r2, rerr2 = tool(home, "lifeos_review", task="T-261116", reviewers="codex,claude", run_id=rid_rev)
    assert not rerr1 and not rerr2
    assert rid_rev in r1 and rid_rev in r2
    assert len(rev_calls) == 2  # once per reviewer on first call, zero on retry
    rm_txt, rm_err = tool(home, "lifeos_review", task="T-261116", reviewers="codex", run_id=rid_rev)
    assert rm_err and rid_rev in rm_txt
    assert len(rev_calls) == 2

    # 6. Concurrent duplicate MCP calls with the same run_id -> 1 provider invocation, 1 terminal record
    conc_calls = []
    barrier = threading.Barrier(4)

    def slow_codex(prompt):
        conc_calls.append(prompt)
        time.sleep(0.05)
        return "Concurrent MCP answer in lifeos/mcp.py. Next step: done."

    monkeypatch.setitem(ask.ADAPTERS, "codex", slow_codex)
    rid_conc = "R-261120-mcpconc1"
    replies = []
    lock = threading.Lock()

    def worker():
        barrier.wait()
        res = tool(home, "lifeos_ask", model="codex", task="T-261116", run_id=rid_conc)
        with lock:
            replies.append(res)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(replies) == 4
    assert all(not is_err and rid_conc in text for text, is_err in replies)
    assert len(conc_calls) == 1
    runs = [
        json.loads(line)
        for line in (home / "logs" / "runs.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert sum(1 for r in runs if r["run_id"] == rid_conc) == 1


def test_mcp_week_log_runs_and_kaizen_tools(home):
    # lifeos_log
    line, err = tool(home, "lifeos_log", action="hours", area="study", hours=2, note="Unit 2 review", date="2026-11-18")
    assert not err and "2026-11-18,study,2,Unit 2 review" in line

    # lifeos_week (markdown, redteam, draft)
    wk_md, err = tool(home, "lifeos_week", week="2026-W47")
    assert not err and "Logged hours: 2.0 h" in wk_md
    rt_md, err = tool(home, "lifeos_week", week="2026-W47", redteam=True)
    assert not err and "# Red-Team Pack · 2026-W47" in rt_md
    dr_msg, err = tool(home, "lifeos_week", week="2026-W47", draft=True)
    assert not err and "2026-W47.md" in dr_msg

    # lifeos_runs
    runs_txt, err = tool(home, "lifeos_runs", limit=5)
    assert not err and "Runs:" in runs_txt

    # lifeos_kaizen
    kzn_txt, err = tool(home, "lifeos_kaizen", month="2026-11")
    assert not err and "# System Health · 2026-11" in kzn_txt
    kzn_dr, err = tool(home, "lifeos_kaizen", month="2026-11", draft=True)
    assert not err and "2026-11.md" in kzn_dr

    # lifeos_route & lifeos_cockpit
    rte_txt, err = tool(home, "lifeos_route", target="T-261116")
    assert not err and "Route Decision" in rte_txt
    ckp_txt, err = tool(home, "lifeos_cockpit")
    assert not err and "cockpit" in ckp_txt





