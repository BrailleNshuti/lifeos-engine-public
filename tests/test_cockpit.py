"""Tests for lifeos/cockpit.py (Braille × LifeOS visual command centre export and localhost API)."""
from http.server import HTTPServer
import json
import urllib.error
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
    assert "Learning Studio" in html
    assert "#focus" in html and "#library" in html and "#recall" in html and "#mastery" in html
    assert "#projects" in html and "#reflect" in html and "#system" in html
    assert "Attempt → Retrieve → Explain → Test → Reflect" in html
    assert "fonts.googleapis.com" not in html and "fonts.gstatic.com" not in html
    assert "T-261116-demo-cli" in html
    assert "AWS Certified Solutions Architect" in html
    data = cockpit.build_cockpit_data(home)
    assert "learning" in data
    assert {"focus_tasks", "due_skills", "mastery_pct", "pack_groups"} <= set(data["learning"])


def test_cockpit_localhost_http_handler_reads_and_logs(home):
    handler = cockpit.make_cockpit_handler(home)
    server = HTTPServer(("127.0.0.1", 0), handler)
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
            headers={"Content-Type": "application/json", "X-LifeOS-Nonce": handler.lifeos_write_nonce},
            method="POST",
        )
        res = json.loads(urllib.request.urlopen(req).read().decode("utf-8"))
        assert res["ok"] is True and "1.5" in res["line"]

        # POST /api/task
        req_task = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/task",
            data=json.dumps({"sentence": "Review cockpit study tab", "level": "L2"}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-LifeOS-Nonce": handler.lifeos_write_nonce},
            method="POST",
        )
        res_task = json.loads(urllib.request.urlopen(req_task).read().decode("utf-8"))
        assert res_task["ok"] is True and "review-cockpit-study-tab" in res_task["path"]

        unauth = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/log",
            data=b'{"action":"hours","area":"study","hours":1}',
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(unauth)
        assert caught.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
