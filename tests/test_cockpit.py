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
    chamber = target / "learning" / "career-mastery" / "project-building-chamber.json"
    chamber.parent.mkdir(parents=True, exist_ok=True)
    chamber.write_text(json.dumps({
        "schema_version": 1,
        "updated": "2026-11-14",
        "region": "Germany / EU",
        "market_signals": [{"name": "Production Python", "why": "Employers need reliable services."}],
        "build_method": [{"stage": "Frame", "done_when": "A measurable problem is written."}],
        "projects": [{
            "id": "F01", "title": "Reliable Python service", "track": "Core", "stage": "Foundation",
            "why": "Proves software fundamentals.", "outcome": "A tested API.", "skills": ["Python"],
            "procedure": ["Define the contract", "Write tests"], "proofs": ["Green CI"],
            "metrics": ["All tests pass"], "interview_questions": ["Why this architecture?"],
        }],
        "interview_rubric": ["Problem", "Ownership", "Metric", "Trade-off", "Learning"],
        "sources": [{"label": "Example careers page", "url": "https://example.com/jobs"}],
    }), encoding="utf-8")
    (target / "cockpit.json").write_text(json.dumps({
        "targets": [{"title": "Example Cloud Practitioner (made up)", "when": "Spring 2030", "detail": "Invented notes"}],
    }), encoding="utf-8")
    return target


def test_cockpit_without_config_shows_neutral_defaults(home):
    (home / "cockpit.json").unlink()
    profile = cockpit.build_cockpit_data(home)["profile"]
    assert profile["targets"] == [] and profile["owner"] == "" and profile["horizon"] == ""
    assert [a["id"] for a in profile["areas"]] == ["study", "lab", "work"]


def test_cockpit_reads_targets_and_labels_from_the_data_home(home):
    (home / "cockpit.json").write_text(json.dumps({
        "owner": "Sam", "focus": "Made-up focus line", "horizon": "Demo milestone (2030-01-01)",
        "targets": [{"title": "Example Cloud Practitioner (made up)", "when": "Spring 2030", "detail": "Invented notes"}],
        "areas": [{"id": "study", "label": "made-up study"}],
    }), encoding="utf-8")
    data = cockpit.build_cockpit_data(home)
    assert data["profile"]["targets"][0]["title"] == "Example Cloud Practitioner (made up)"
    assert data["profile"]["areas"] == [{"id": "study", "label": "made-up study"}]
    assert "Example Cloud Practitioner (made up)" in cockpit.render_cockpit_html(home)


def test_cockpit_broken_config_falls_back_to_defaults(home):
    (home / "cockpit.json").write_text("{not json", encoding="utf-8")
    assert cockpit.build_cockpit_data(home)["profile"]["targets"] == []
    (home / "cockpit.json").write_text(json.dumps({"targets": "nope", "areas": [1, {"label": "no id"}]}), encoding="utf-8")
    profile = cockpit.build_cockpit_data(home)["profile"]
    assert profile["targets"] == [] and [a["id"] for a in profile["areas"]] == ["study", "lab", "work"]


def test_cockpit_export_creates_self_contained_html_and_passes_guard(home, capsys):
    assert main(["--home", str(home), "cockpit"]) == 0
    out_rel = capsys.readouterr().out.strip().replace("\\", "/")
    assert out_rel == "cockpit/index.html"
    html_path = home / "cockpit" / "index.html"
    assert html_path.exists()
    html = html_path.read_text(encoding="utf-8")
    assert "Braille × LifeOS · cockpit" in html
    assert "Private Study Atelier" in html
    assert 'data-tab="learning"' in html and 'data-tab="study"' in html
    assert 'data-tab="practice"' in html and 'data-tab="exam"' in html and 'data-tab="mastery"' in html
    assert "#projects" in html and "#reflect" in html and "#system" in html
    assert "#build" in html and "Project Building Chamber" in html
    assert 'data-tab="communications"' in html and "Communication Hub" in html
    assert "explicit confirmation" in html and "lifeos_reply_draft_v1" in html
    assert "Learning Journey" in html and "Evidence streak" in html
    assert "/api/study/submit" in html and "/api/study/refresh" in html
    assert "Capture → Learn → Recall → Exam → Reflect" in html
    assert "fonts.googleapis.com" not in html and "fonts.gstatic.com" not in html
    assert "T-261116-demo-cli" in html
    assert "Example Cloud Practitioner (made up)" in html
    data = cockpit.build_cockpit_data(home)
    assert "learning" in data
    assert {"focus_tasks", "due_skills", "mastery_pct", "pack_groups"} <= set(data["learning"])
    assert {"sources", "banks", "trust_counts", "due"} <= set(data["study_engine"])
    assert {"curricula", "gaps", "streak"} <= set(data["study_engine"])
    assert data["project_chamber"]["projects"][0]["id"] == "F01"
    assert data["communications"]["policy"]["send"] == "explicit_confirmation"
    assert {channel["id"] for channel in data["communications"]["channels"]} == {"gmail", "outlook", "whatsapp"}


def test_cockpit_dark_theme_has_explicit_readable_foregrounds():
    """Protect the actual aliases consumed by components, not only the palette tokens."""
    html = cockpit.COCKPIT_HTML_TEMPLATE
    night = html.split("body.night{", 1)[1].split("}", 1)[0]
    expected = {
        "--text": "#F4F7FB",
        "--mute": "#B9C3D2",
        "--paper": "#111722",
        "--desk": "#080B12",
        "--line": "#2E3A4C",
    }
    for name, value in expected.items():
        assert f"{name}:{value}" in night
    assert "body.night .btn.primary{color:#0A0C12}" in html
    assert ".input::placeholder{color:var(--faint)" in html
    assert ".nav.on{border-left:0;border-bottom-color:var(--blue)}" in html


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

        # Source-grounded study pipeline: note -> bank -> verify -> answer -> attempt -> exam.
        req_note = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/study/note",
            data=json.dumps({
                "title": "Python Functions", "subject": "Python",
                "content": "## Return values\nA return statement sends a value back to the caller.",
            }).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-LifeOS-Nonce": handler.lifeos_write_nonce}, method="POST",
        )
        note = json.loads(urllib.request.urlopen(req_note).read().decode("utf-8"))
        assert note["path"].startswith("learning/sources/")
        req_bank = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/study/bank",
            data=json.dumps({"source": note["path"]}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-LifeOS-Nonce": handler.lifeos_write_nonce}, method="POST",
        )
        bank_result = json.loads(urllib.request.urlopen(req_bank).read().decode("utf-8"))
        state = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state").read().decode("utf-8"))
        question = next(b for b in state["study_engine"]["banks"] if b["path"] == bank_result["path"])["questions"][0]
        assert "answer" not in question
        req_review = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/study/review-answer",
            data=json.dumps({"question_id": question["id"]}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-LifeOS-Nonce": handler.lifeos_write_nonce}, method="POST",
        )
        assert "sends a value" in json.loads(urllib.request.urlopen(req_review).read().decode("utf-8"))["answer"]
        req_verify = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/study/trust",
            data=json.dumps({"bank": bank_result["path"], "question_id": question["id"], "trust": "verified"}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-LifeOS-Nonce": handler.lifeos_write_nonce}, method="POST",
        )
        assert json.loads(urllib.request.urlopen(req_verify).read().decode("utf-8"))["trust"] == "verified"
        req_answer = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/study/answer",
            data=json.dumps({"question_id": question["id"]}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-LifeOS-Nonce": handler.lifeos_write_nonce}, method="POST",
        )
        assert "sends a value" in json.loads(urllib.request.urlopen(req_answer).read().decode("utf-8"))["answer"]
        req_attempt = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/study/attempt",
            data=json.dumps({"question_id": question["id"], "rating": "good", "elapsed_seconds": 25}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-LifeOS-Nonce": handler.lifeos_write_nonce}, method="POST",
        )
        assert json.loads(urllib.request.urlopen(req_attempt).read().decode("utf-8"))["interval_days"] == 4
        req_exam = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/study/exam",
            data=json.dumps({"title": "Python Check", "subject": "python", "count": 1, "minutes": 10}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-LifeOS-Nonce": handler.lifeos_write_nonce}, method="POST",
        )
        assert json.loads(urllib.request.urlopen(req_exam).read().decode("utf-8"))["exam_path"].startswith("reviews/exam-")

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
