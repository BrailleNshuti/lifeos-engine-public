"""`verify-quotes` also reads long backtick spans (Gemini quotes lines that way); the free CHECK line does not, so a code
span in an answer is never reported as a missing quote."""
import shutil

import pytest

from lifeos import check
from lifeos.cli import main

LINE = "An idea counts only if it survives on evidence in this document"
OTHER = "This sentence is nowhere in the document that was given"


def test_backtick_spans_are_checked_when_asked():
    source = "padding " * 10 + LINE
    found, missing = check.quote_report(f"It says `{LINE}` and `{OTHER}`.", source, backticks=True)
    assert found == [LINE] and missing == [OTHER]


def test_they_are_ignored_by_default():
    assert check.quote_report(f"`{LINE}`", "unrelated") == ([], [])


def test_short_code_spans_are_never_quotes():
    found, missing = check.quote_report("run `pytest -q tests/` and `lifeos/store.py`", "nothing", backticks=True)
    assert (found, missing) == ([], [])


def test_a_span_without_a_space_is_a_path_not_a_quote():
    path = "lifeos/some/very/long/module/name/that/goes/on/and/on/file.py"
    assert check.quote_report(f"see `{path}`", "x", backticks=True) == ([], [])


def test_the_free_check_does_not_flag_a_long_code_span():
    text = "Run `python -m pytest tests/test_alpha.py tests/test_beta.py -q` now. Read 2026-11-27. Next step: none."
    assert not any("quoted" in f for f in check.check_answer(text, source="padding " * 300))


@pytest.fixture
def home(tmp_path, demo, monkeypatch):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    monkeypatch.setenv("LIFEOS_HOME", str(target))
    return target


def test_the_command_reports_a_missing_backtick_quote(home, capsys):
    task = home / "tasks" / "T-261116-demo-cli.md"
    raw = task.read_text(encoding="utf-8").split("\n## Result", 1)[0]
    raw = raw.replace("## Context (links, not essays)\n", f"## Context (links, not essays)\n{LINE}\n", 1)
    task.write_text(raw + f"\n## Result · fake · 2026-11-27\nIt says `{LINE}` and `{OTHER}`. Next step: none.\n", encoding="utf-8")
    assert main(["verify-quotes", "T-261116"]) == 1
    out = capsys.readouterr().out
    assert "1 of 2" in out and OTHER[:30] in out
