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
