import datetime as dt
import json
import shutil

import pytest

from lifeos import mistakes, study, vocab
from lifeos.cli import main

D = dt.date(2026, 11, 23)


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def bank_with_questions(home, n=3):
    folder = home / "learning" / "question-banks"
    folder.mkdir(parents=True)
    qs = [{"id": f"q{i}", "prompt": f"Prompt {i}?", "answer": f"Answer {i}", "trust": "verified",
           "citation": "learning/sources/x.md:L1", "source_sha256": "0" * 64} for i in range(n)]
    (folder / "b.json").write_text(json.dumps({"schema_version": 1, "source": {}, "questions": qs}), encoding="utf-8")


def attempt(home, qid, rating, day="2026-11-20"):
    row = {"question_id": qid, "rating": rating, "date": day}
    path = home / "logs" / "study-attempts.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def test_quiz_ranks_worst_first_and_hides_answers(home):
    bank_with_questions(home)
    for r in ("again", "again", "good"):
        attempt(home, "q0", r)
    attempt(home, "q1", "hard")
    attempt(home, "q2", "easy")
    quiz = mistakes.quiz(home, count=5)
    assert [q["id"] for q in quiz] == ["q0", "q1"]  # two misses outweigh one hard; q2 was easy
    assert "q2" not in [q["id"] for q in quiz]
    assert all("answer" not in q for q in quiz)


def test_a_question_fixed_by_later_good_answers_drops_out(home):
    bank_with_questions(home, 1)
    attempt(home, "q0", "again")
    attempt(home, "q0", "good")
    attempt(home, "q0", "good")
    assert mistakes.quiz(home) == []


def test_no_attempts_means_empty_quiz(home):
    assert mistakes.quiz(home) == []


def test_vocab_add_quiz_answer_cycle(home):
    vocab.add(home, "die Wohnung", "the flat", "Meine Wohnung ist in Bonn.", today=D)
    with pytest.raises(vocab.VocabError):
        vocab.add(home, "die Wohnung", "the flat", today=D)
    assert [w["word"] for w in vocab.due(home, today=D)] == ["die Wohnung"]
    vocab.answer(home, "die Wohnung", True, today=D)
    assert vocab.due(home, today=D) == []
    assert vocab.due(home, today=D + dt.timedelta(days=1))[0]["word"] == "die Wohnung"
    vocab.answer(home, "die Wohnung", False, today=D + dt.timedelta(days=1))
    assert vocab.stats(home)["words"][0]["box"] == 0


def test_vocab_refuses_private_data_and_unknown_word(home):
    with pytest.raises(vocab.VocabError):
        vocab.add(home, "Schlüssel", "key sk-ant-api03-" + "a1B2c3D4" * 5, today=D)
    with pytest.raises(vocab.VocabError):
        vocab.answer(home, "nope", True, today=D)


def test_cli(home, capsys, monkeypatch):
    monkeypatch.setenv("LIFEOS_HOME", str(home))
    bank_with_questions(home, 1)
    attempt(home, "q0", "again")
    assert main(["mistakes"]) == 0
    assert "Prompt 0?" in capsys.readouterr().out
    assert main(["vocab", "add", "der Mietvertrag", "rental contract"]) == 0
    assert main(["vocab", "quiz"]) == 0
    assert "der Mietvertrag" in capsys.readouterr().out
    assert main(["vocab", "answer", "der Mietvertrag", "good"]) == 0
    assert main(["vocab", "answer", "unknown", "good"]) == 2
