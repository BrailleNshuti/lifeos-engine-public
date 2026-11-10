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
