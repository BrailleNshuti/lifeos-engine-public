"""Tests for lifeos/exam.py, lifeos/bakeoff.py, and lifeos/showcase.py (CLI + MCP)."""
import io
import json
import shutil

import pytest

from lifeos import bakeoff, exam, mcp, showcase
from lifeos.cli import main


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def test_exam_generate_draft_and_record_score(home, capsys):
    assert "MONTHLY NO-AI EXAM" in exam.generate_monthly_exam(home, month="2026-11")
    # 1. Print exam to stdout
    assert main(["--home", str(home), "exam", "--month", "2026-11"]) == 0
    out = capsys.readouterr().out
    assert "MONTHLY NO-AI EXAM · 2026-11" in out
    assert "Part 1 · Three Short-Answer Retrieval Questions" in out

    # 2. Write draft file
    assert main(["--home", str(home), "exam", "--month", "2026-11", "--draft"]) == 0
    rel = capsys.readouterr().out.strip().replace("\\", "/")
    assert rel == "reviews/exam-2026-11.md"
    assert (home / "reviews" / "exam-2026-11.md").exists()

    # 3. Record graded exam score >= 80% elevates skill to Level 3 in logs/skills.md
    assert main([
        "--home", str(home), "exam",
        "--score-skill", "Python engineering",
        "--score-pct", "88",
        "--link", "reviews/exam-2026-11.md",
    ]) == 0
    res = json.loads(capsys.readouterr().out)
    assert res["elevated_to_level_3"] is True
    skills_txt = (home / "logs" / "skills.md").read_text(encoding="utf-8")
    assert "| Python engineering | 3 |" in skills_txt
    assert "88%" in skills_txt


def test_bakeoff_blind_pair_and_scorecard(home, capsys):
    assert set(bakeoff.blind_pair("2026-Q4", "Decision Memo", "claude", "chatgpt")) == {"X", "Y", "blind_hash"}
    scores = json.dumps({
        "X": {"t1": [5, 5, 4, 4], "t2": [5, 4, 4, 4], "t3": [4, 4, 4, 4]},
        "Y": {"t1": [3, 4, 3, 4], "t2": [3, 3, 4, 4], "t3": [4, 3, 3, 4]},
    })
    assert main([
        "--home", str(home), "bakeoff",
        "--quarter", "2026-Q4",
        "--task-type", "Decision Memo",
        "--scores", scores,
        "--draft",
    ]) == 0
    rel = capsys.readouterr().out.strip().replace("\\", "/")
    assert rel == "reviews/bakeoff-2026-Q4-decision-memo.md"
    text = (home / "reviews" / "bakeoff-2026-Q4-decision-memo.md").read_text(encoding="utf-8")
    assert "ROLE BAKE-OFF · 2026-Q4" in text
    assert "Winner (2 of 3 rule)" in text


def test_showcase_generates_and_drafts_weekly_post(home, capsys):
    assert "#AIEngineering" in showcase.generate_weekly_post(home, week="2026-W46")
    assert main(["--home", str(home), "showcase", "--week", "2026-W46", "--draft"]) == 0
    rel = capsys.readouterr().out.strip().replace("\\", "/")
    assert rel == "reviews/post-2026-W46.md"
    post_txt = (home / "reviews" / "post-2026-W46.md").read_text(encoding="utf-8")
    assert "BUILD IN PUBLIC" in post_txt
    assert "#AIEngineering" in post_txt


def test_mcp_exposes_exam_bakeoff_and_showcase(home):
    req_list = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    res_list = mcp.handle(home, req_list)
    names = {t["name"] for t in res_list["result"]["tools"]}
    assert {"lifeos_exam", "lifeos_bakeoff", "lifeos_showcase"} <= names

    # Call lifeos_showcase via MCP
    req_call = {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "lifeos_showcase", "arguments": {"week": "2026-W46", "draft": True}},
    }
    res_call = mcp.handle(home, req_call)
    assert res_call["result"]["isError"] is False
    assert "drafted reviews" in res_call["result"]["content"][0]["text"].replace("\\", "/")
