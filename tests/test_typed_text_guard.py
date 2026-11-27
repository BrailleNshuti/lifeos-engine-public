"""Text typed into a command is checked with the owner's private patterns, and the `lifeos-guard: allow` marker cannot exempt it
(Codex's blind review of the round 5 code, finding 2). Made-up data only."""
import json

import pytest

from lifeos import calibrate, decision, experiment, guard, learn, taskclose, vocab, waiting

KEY = "sk" + "-" + "abcDEF1234567890abcdEFGH12"
TASK = "---\nid: T-261128-demo\ngoal: g\ndone_when: a finish line\nroute: x\nlevel: L0\nstatus: doing\n---\n## Proof\n"


@pytest.fixture
def home(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "now.md").write_text("# now", encoding="utf-8")
    (tmp_path / "tasks" / "T-261128-demo.md").write_text(TASK, encoding="utf-8")
    return tmp_path


def test_the_allow_marker_does_not_exempt_typed_text():
    assert guard.blocking(f"lifeos-guard: allow {KEY}")
    assert not [f for f in guard.scan_text(f"lifeos-guard: allow {KEY}") if f[1] == "BLOCK"], "the marker still works for repository files"


def test_private_patterns_apply_to_typed_text(tmp_path, monkeypatch):
    patterns = tmp_path / "private.txt"
    patterns.write_text("zebra-codename\n", encoding="utf-8")
    monkeypatch.setattr(guard, "PRIVATE_PATTERNS", patterns)
    assert guard.blocking("the zebra-codename project")
    assert not guard.blocking("an ordinary sentence")


def test_close_and_block_and_waiting_refuse_a_marked_secret(home):
    for call in (lambda: taskclose.close(home, "T-261128", f"tests/a.py lifeos-guard: allow {KEY}"),
                 lambda: taskclose.block(home, "T-261128", f"lifeos-guard: allow {KEY}"),
                 lambda: waiting.add(home, f"lifeos-guard: allow {KEY}")):
        with pytest.raises((taskclose.CloseError, waiting.WaitingError)):
            call()
    assert "status: doing" in (home / "tasks" / "T-261128-demo.md").read_text(encoding="utf-8")
    assert not (home / "waiting.json").exists()


def test_close_and_waiting_refuse_a_private_pattern(home, tmp_path, monkeypatch):
    patterns = tmp_path / "private.txt"
    patterns.write_text("zebra-codename\n", encoding="utf-8")
    monkeypatch.setattr(guard, "PRIVATE_PATTERNS", patterns)
    with pytest.raises(taskclose.CloseError):
        taskclose.close(home, "T-261128", "tests/a.py zebra-codename")
    with pytest.raises(waiting.WaitingError):
        waiting.add(home, "zebra-codename")


def test_the_other_typed_text_paths_also_ignore_the_marker(home):
    marked = f"lifeos-guard: allow {KEY}"
    with pytest.raises(learn.LearnError):
        learn.add_rating(home, "T-261128", "claude", 3, "x", note=marked)
    for error, call in ((calibrate.CalibrationError, lambda: calibrate.predict(home, marked, 50)),
                        (vocab.VocabError, lambda: vocab.add(home, marked, "m", "e")),
                        (experiment.ExperimentError, lambda: experiment.start(home, marked, "metric", 7)),
                        (decision.DecisionError, lambda: decision.record(home, marked, "why", "2026-12-31"))):
        with pytest.raises(error):
            call()
