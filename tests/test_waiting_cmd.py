"""`lifeos waiting`: add, list and remove entries of waiting.json without hand editing. Made-up data only."""
import json

import pytest

from lifeos import waiting
from lifeos.cli import main


@pytest.fixture
def home(tmp_path):
    (tmp_path / "logs").mkdir()
    (tmp_path / "now.md").write_text("# now", encoding="utf-8")
    return tmp_path


def test_add_list_and_done_round_trip(home, capsys):
    assert main(["--home", str(home), "waiting", "add", "Pick a date for the demo", "--who", "you", "--when", "2026-12-01"]) == 0
    assert main(["--home", str(home), "waiting", "add", "Wait for the RAM", "--who", "Claude"]) == 0
    capsys.readouterr()
    assert main(["--home", str(home), "waiting", "list"]) == 0
    out = capsys.readouterr().out
    assert " 1. Pick a date for the demo  (you, 2026-12-01)" in out and " 2. Wait for the RAM  (Claude, anytime)" in out
    assert main(["--home", str(home), "waiting", "done", "1"]) == 0
    assert [r["item"] for r in waiting.read(home)] == ["Wait for the RAM"]


def test_the_file_stays_a_plain_json_list_that_today_can_read(home):
    from lifeos import today
    waiting.add(home, "one thing", who="you", when="soon")
    assert json.loads((home / "waiting.json").read_text(encoding="utf-8")) == [{"item": "one thing", "who": "you", "when": "soon"}]
    assert today.read_waiting(home)[0]["item"] == "one thing"


def test_a_damaged_file_is_never_overwritten(home, capsys):
    (home / "waiting.json").write_text("{not json", encoding="utf-8")
    assert main(["--home", str(home), "waiting", "add", "x"]) == 2
    assert "not valid JSON" in capsys.readouterr().err
    assert (home / "waiting.json").read_text(encoding="utf-8") == "{not json"


def test_empty_long_and_secret_items_and_bad_numbers_are_refused(home):
    for bad in ("", "  ", "x" * 401, "key " + "sk" + "-" + "abcDEF1234567890abcdEFGH12"):
        with pytest.raises(waiting.WaitingError):
            waiting.add(home, bad)
    with pytest.raises(waiting.WaitingError, match="no entry"):
        waiting.remove(home, 3)
    assert not (home / "waiting.json").exists()


def test_an_empty_list_says_so(home, capsys):
    main(["--home", str(home), "waiting", "list"])
    assert "Nothing is waiting." in capsys.readouterr().out


def test_two_processes_adding_lose_nothing(home):
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    code = "import sys; sys.path.insert(0, sys.argv[3]); from lifeos import waiting; [waiting.add(sys.argv[1], f'{sys.argv[2]}-{i}') for i in range(15)]"
    procs = [subprocess.Popen([sys.executable, "-c", code, str(home), tag, str(root)], stderr=subprocess.PIPE, text=True) for tag in ("a", "b")]
    for p in procs:
        assert p.wait(timeout=120) == 0, p.stderr.read()[-300:]
    assert len(waiting.read(home)) == 30


# Found by a blind review (Gemini, 2026-11-27) and confirmed by hand against the code.
@pytest.mark.parametrize("damaged", [[{"item": "ok", "who": "you", "when": "x"}, {"itme": "typo"}], ["a plain string"], [5], [{"item": 7}]])
def test_a_damaged_entry_stops_add_and_done_and_nothing_is_erased(home, damaged, capsys):
    text = json.dumps(damaged)
    (home / "waiting.json").write_text(text, encoding="utf-8")
    assert main(["--home", str(home), "waiting", "add", "new"]) == 2
    assert main(["--home", str(home), "waiting", "done", "1"]) == 2
    assert "entry" in capsys.readouterr().err
    assert (home / "waiting.json").read_text(encoding="utf-8") == text


def test_reading_a_missing_file_is_empty_and_an_unreadable_one_is_not_called_invalid_json(home, monkeypatch):
    assert waiting.read(home) == []
    (home / "waiting.json").write_text("[]", encoding="utf-8")

    def gone(path):
        raise FileNotFoundError("deleted between the check and the read")
    monkeypatch.setattr(waiting, "read_bytes_retry", gone)
    assert waiting.read(home) == []

    def locked(path):
        raise PermissionError(13, "locked")
    monkeypatch.setattr(waiting, "read_bytes_retry", locked)
    with pytest.raises(waiting.WaitingError, match="Could not read"):
        waiting.read(home)
