"""Tests for lifeos/cockpit.py (Braille × LifeOS visual command centre export and localhost API)."""
from http.server import HTTPServer
import json
import shutil
import threading
import urllib.request

import pytest

from lifeos import cockpit
from lifeos.cli import main


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def test_cockpit_export_creates_self_contained_html_and_passes_guard(home, capsys):
    assert main(["--home", str(home), "cockpit"]) == 0
    out_rel = capsys.readouterr().out.strip().replace("\\", "/")
    assert out_rel == "cockpit/index.html"
    html_path = home / "cockpit" / "index.html"
    assert html_path.exists()
    html = html_path.read_text(encoding="utf-8")
    assert "Braille × LifeOS · cockpit" in html
    assert "#today" in html and "#tasks" in html and "#study" in html and "#career" in html and "#agents" in html and "#loops" in html
    assert "T-261116-demo-cli" in html
    assert "AWS Certified Solutions Architect" in html


def test_cockpit_localhost_http_handler_reads_and_logs(home):
    server = HTTPServer(("127.0.0.1", 0), cockpit.make_cockpit_handler(home))
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # GET /
        html = urllib.request.urlopen(f"http://127.0.0.1:{port}/").read().decode("utf-8")
        assert "Braille × LifeOS · cockpit" in html

        # GET /api/state
        state = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state").read().decode("utf-8"))
        assert "week" in state and "tasks" in state

        # POST /api/log (hours)
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/log",
            data=json.dumps({"action": "hours", "area": "study", "hours": 1.5, "note": "Cockpit test"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        res = json.loads(urllib.request.urlopen(req).read().decode("utf-8"))
        assert res["ok"] is True and "1.5" in res["line"]

        # POST /api/task
        req_task = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/task",
            data=json.dumps({"sentence": "Review cockpit study tab", "level": "L2"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        res_task = json.loads(urllib.request.urlopen(req_task).read().decode("utf-8"))
        assert res_task["ok"] is True and "review-cockpit-study-tab" in res_task["path"]
    finally:
        server.shutdown()
        server.server_close()
