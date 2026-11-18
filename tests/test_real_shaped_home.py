"""A made-up home with the quirks the first real run showed: a level followed by a note, a TODO placeholder,
Windows line endings, and older ledger records from before the chain. The Sunday pipeline must fail only on the
placeholder, say so in one summary line, and pass once it is filled in."""
import json
import shutil

import pytest

from lifeos import verify
from lifeos.cli import main

TASK = ("---\nid: {id}\ngoal: Look it up\ndone_when: {done}\nroute: Grok\nlevel: {level}\nstatus: doing\ndue: 2026-11-30\n---\n"
        "## Proof\n")


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    tasks = target / "tasks"
    for name, done, level in [("T-261110-cleanup", "repo renamed and checked", "L2 (renames and other public changes are L3: my yes)"),
                              ("T-261117-price", "TODO", "L0"), ("T-261117-price-2", "TODO", "L0")]:
        text = TASK.format(id=name, done=done, level=level).replace("\n", "\r\n")
        (tasks / f"{name}.md").write_bytes(text.encode("utf-8"))
    old = [json.dumps({"run_id": f"R-old-{i}", "command": "ask", "ts": "2026-11-0%d" % (i + 1)}).encode() for i in range(4)]
    (target / "logs").mkdir(exist_ok=True)
    (target / "logs" / "runs.jsonl").write_bytes(b"\r\n".join(old) + b"\r\n")
    return target


def test_the_sunday_pipeline_fails_only_on_the_placeholders_then_passes(home, capsys):
    assert main(["--home", str(home), "pipeline", "sunday", "--run"]) == 1
    out = capsys.readouterr().out
    assert "failed   task files" in out and out.count("failed") == 2  # the step and the summary line
    assert "Summary: 5 ok, 1 failed. Exit code 1." in out
    assert "level:" not in out  # the level with a note is not a problem
    for name in ("T-261117-price", "T-261117-price-2"):
        path = home / "tasks" / f"{name}.md"
        path.write_bytes(path.read_bytes().replace(b"done_when: TODO", b"done_when: price and source with date written"))
    assert main(["--home", str(home), "pipeline", "sunday", "--run"]) == 0
    assert "Summary: 6 ok. Exit code 0." in capsys.readouterr().out


def test_older_records_in_crlf_are_legacy_and_a_seal_pins_them(home, capsys):
    result = verify.verify_chain(home)
    assert result["ok"] and result["legacy"] == 4 and result["chained"] == 0
    assert main(["--home", str(home), "verify", "--seal"]) == 0
    path = home / "logs" / "runs.jsonl"
    path.write_bytes(path.read_bytes().replace(b"R-old-2", b"R-old-9"))
    assert main(["--home", str(home), "verify"]) == 1
    assert "the seal" in capsys.readouterr().out
