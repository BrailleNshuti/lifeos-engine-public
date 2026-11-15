"""Tests for the local-first source → question → practice → exam pipeline."""
import json
import shutil

import pytest

from lifeos import study
from lifeos.cli import main


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def seed_source(home):
    source = home / "learning" / "sources" / "python-basics.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        """---
title: Python Basics
subject: Python
---
# Python Basics

## Functions
Functions package reusable behavior. Parameters are inputs and return values are outputs.

## Exceptions
Exceptions separate the normal path from error handling. Catch only errors you can handle.

Q: What does a return statement do?
A: It ends the function call and sends a value to the caller.
Key points: ends the function call | sends a value | caller
""",
        encoding="utf-8",
    )
    key = home / "learning" / "sources" / "python-basics-key.md"
    key.write_text("# Hidden answer key\n", encoding="utf-8")
    return source


def test_note_library_excludes_keys_and_saves_guarded_note(home):
    seed_source(home)
    note = study.save_note(home, "Joins", "SQL", "## Inner join\nAn inner join keeps matching rows.")
    assert note.relative_to(home).as_posix() == "learning/sources/sql--joins.md"
    sources = study.list_sources(home, include_content=True)
    paths = {row["path"] for row in sources}
    assert "learning/sources/python-basics.md" in paths
    assert "learning/sources/python-basics-key.md" not in paths
    assert "learning/sources/sql--joins.md" in paths
    assert next(row for row in sources if row["path"].endswith("sql--joins.md"))["content"].startswith("# Joins")

    with pytest.raises(study.StudyError, match="privacy guard"):
        study.save_note(home, "Secret", "test", "synthetic token: " + "ghp_" + ("A" * 36))
    with pytest.raises(study.StudyError, match="already exists"):
        study.save_note(home, "Joins", "SQL", "duplicate")


def test_grounded_bank_requires_human_verification_before_practice(home):
    source = seed_source(home)
    target = study.write_question_bank(home, source.relative_to(home).as_posix())
    bank = json.loads(target.read_text(encoding="utf-8"))
    assert bank["questions"]
    assert {q["trust"] for q in bank["questions"]} == {"grounded"}
    first = bank["questions"][0]
    assert first["citation"].startswith("learning/sources/python-basics.md:L")
    assert ":L13-L14" in first["citation"]

    snapshot = study.study_snapshot(home)
    assert snapshot["due_count"] == 0
    assert all("answer" not in q for row in snapshot["banks"] for q in row["questions"])
    with pytest.raises(study.StudyError, match="verified or trusted"):
        study.record_attempt(home, first["id"], "good")

    review = study.get_question_for_review(home, first["id"])
    assert review["trust"] == "grounded" and review["answer"]

    verified = study.set_question_trust(home, target.relative_to(home).as_posix(), first["id"], "verified")
    assert verified["trust"] == "verified"
    answer = study.get_question_answer(home, first["id"])
    assert answer["answer"] and answer["citation"]
    attempt = study.record_attempt(home, first["id"], "good", elapsed_seconds=42)
    assert attempt["interval_days"] == 4 and attempt["elapsed_seconds"] == 42
    assert study.study_snapshot(home)["due_count"] == 0


def test_verification_refuses_stale_source_and_exam_writes_separate_key(home):
    source = seed_source(home)
    target = study.write_question_bank(home, source.relative_to(home).as_posix())
    bank = json.loads(target.read_text(encoding="utf-8"))
    source.write_text(source.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
    with pytest.raises(study.StudyError, match="Source changed"):
        study.set_question_trust(home, target.relative_to(home).as_posix(), bank["questions"][0]["id"], "verified")

    target.unlink()
    target = study.write_question_bank(home, source.relative_to(home).as_posix())
    bank = json.loads(target.read_text(encoding="utf-8"))
    for question in bank["questions"][:2]:
        study.set_question_trust(home, target.relative_to(home).as_posix(), question["id"], "verified")
    result = study.compose_exam(home, title="Python Check", subject="python", count=2, minutes=20)
    exam = result["exam_path"].read_text(encoding="utf-8")
    key = result["key_path"].read_text(encoding="utf-8")
    assert "Your answer:" in exam and "Functions package" not in exam
    assert "answer key" in key.lower() and result["question_count"] == 2
    assert result["exam_path"].parent.name == "reviews"
    assert result["key_path"].parent.name == "exam-keys"


def test_study_paths_and_ratings_are_strict(home):
    with pytest.raises(study.StudyError, match="allowed"):
        study.build_question_candidates(home, "../rules.md")
    with pytest.raises(study.StudyError, match="integers"):
        study.compose_exam(home, count="many")
    with pytest.raises(study.StudyError, match="Rating"):
        study.record_attempt(home, "missing", "perfect")


def test_study_cli_lists_sources_and_builds_bank(home, capsys):
    source = seed_source(home)
    assert main(["--home", str(home), "study", "sources"]) == 0
    assert "python-basics.md" in capsys.readouterr().out
    assert main(["--home", str(home), "study", "bank", source.relative_to(home).as_posix()]) == 0
    assert "learning/question-banks/" in capsys.readouterr().out.replace("\\", "/")


def test_curriculum_refresh_answer_scoring_gaps_and_streak(home):
    source = seed_source(home)
    curriculum_dir = home / "learning" / "curricula"
    curriculum_dir.mkdir(parents=True, exist_ok=True)
    (curriculum_dir / "python.json").write_text(json.dumps({
        "schema_version": 1, "id": "python", "title": "Python", "skill": "Python engineering",
        "steps": [{"id": "py-01", "title": "Functions", "source_path": source.relative_to(home).as_posix(),
                   "outcomes": ["Explain return values"]}],
    }), encoding="utf-8")

    curricula = study.list_curricula(home)
    assert curricula[0]["steps"][0]["source_path"] == "learning/sources/python-basics.md"
    refreshed = study.refresh_question_banks(home, "python")
    assert refreshed["created"] == 1 and refreshed["needs_verification"] >= 1
    bank_path = home / refreshed["paths"][0]
    bank = json.loads(bank_path.read_text(encoding="utf-8"))
    question = next(q for q in bank["questions"] if q.get("key_points"))
    study.set_question_trust(home, refreshed["paths"][0], question["id"], "verified")

    result = study.submit_answer(home, question["id"], "It ends the function call and sends a value back to the caller.", 18)
    assert result["recorded"] is True
    assert result["evaluation"]["score"] == 1.0
    snapshot = study.study_snapshot(home)
    assert snapshot["attempt_count"] == 1 and snapshot["streak"]["current"] == 1
    assert snapshot["curricula"][0]["progress_pct"] == 100
    assert all("response" not in gap for gap in snapshot["gaps"])


def test_submit_answer_records_missing_concepts_without_exporting_response(home):
    source = seed_source(home)
    bank_path = study.write_question_bank(home, source.relative_to(home).as_posix())
    bank = json.loads(bank_path.read_text(encoding="utf-8"))
    question = next(q for q in bank["questions"] if q.get("key_points"))
    study.set_question_trust(home, bank_path.relative_to(home).as_posix(), question["id"], "verified")
    result = study.submit_answer(home, question["id"], "It only sends something somewhere.")
    assert result["recorded"] is True and result["evaluation"]["missing_concepts"]
    raw = (home / "logs" / "study-attempts.jsonl").read_text(encoding="utf-8")
    assert "It only sends" in raw
    snapshot_text = json.dumps(study.study_snapshot(home))
    assert "It only sends" not in snapshot_text
