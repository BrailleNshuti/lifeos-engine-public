import shutil

from lifeos.cli import main


def test_week_and_doctor(demo, capsys):
    assert main(["--home", str(demo), "week", "--week", "2026-W47"]) == 0
    assert "Proofs: 3" in capsys.readouterr().out
    assert main(["--home", str(demo), "doctor"]) == 0
    assert "doctor: ok" in capsys.readouterr().out


def test_guard_exit_codes(tmp_path):
    leak = tmp_path / "leak.md"
    leak.write_text("token " + "ghp_" + "a1" * 18)
    clean = tmp_path / "clean.md"
    clean.write_text("nothing secret here")
    assert main(["guard", str(leak)]) == 1
    assert main(["guard", str(clean)]) == 0


def test_task_new_and_missing_home(tmp_path, capsys):
    (tmp_path / "now.md").write_text("# Now")
    assert main(["--home", str(tmp_path), "task", "new", "Draft", "the", "demo", "checklist"]) == 0
    assert "demo-checklist" in capsys.readouterr().out
    assert main(["--home", str(tmp_path / "nope"), "week"]) == 2


def test_doctor_fails_when_core_exceeds_token_cap(demo, tmp_path, capsys):
    home = tmp_path / "home"
    shutil.copytree(demo, home)
    (home / "now.md").write_text("# Now\n" + "word " * 9000 + "\n")
    assert main(["--home", str(home), "doctor"]) == 1
    out = capsys.readouterr().out
    assert "over the 2000-token cap" in out
    assert "doctor: 1 thing(s) to fix" in out
