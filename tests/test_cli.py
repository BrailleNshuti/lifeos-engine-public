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


def test_task_commands_refuse_secrets_from_the_command_line(tmp_path, capsys):
    iban = "DE89 3704 " + "0044 0532 0130 00"
    (tmp_path / "now.md").write_text("# Now", encoding="utf-8")
    assert main(["--home", str(tmp_path), "task", "new", "Pay", "rent", "to", iban]) == 2
    assert not (tmp_path / "tasks").exists()

    tasks = tmp_path / "tasks"
    tasks.mkdir()
    task = tasks / "T-261128-demo.md"
    original = "---\nid: T-261128-demo\ndone_when: tests pass\nstatus: inbox\n---\n## Proof\n"
    task.write_text(original, encoding="utf-8")
    assert main(["--home", str(tmp_path), "task", "close", task.stem, "--proof", f"tests/a.py {iban}"]) == 2
    assert task.read_text(encoding="utf-8") == original
    assert "private data" in capsys.readouterr().err


def test_doctor_fails_when_core_exceeds_token_cap(demo, tmp_path, capsys):
    home = tmp_path / "home"
    shutil.copytree(demo, home)
    (home / "now.md").write_text("# Now\n" + "word " * 9000 + "\n")
    assert main(["--home", str(home), "doctor"]) == 1
    out = capsys.readouterr().out
    assert "over the 2000-token cap" in out
    assert "doctor: 1 thing(s) to fix" in out


def test_context_explain_and_doctor_tools_and_review_dry_run(demo, capsys, monkeypatch):
    monkeypatch.setattr("lifeos.ask.shutil.which", lambda name: f"/bin/{name}")
    assert main(["--home", str(demo), "context", "T-261116", "--explain"]) == 0
    assert "sha256" in capsys.readouterr().out
    assert main(["--home", str(demo), "doctor", "--tools"]) == 0
    assert "Providers:" in capsys.readouterr().out
    assert main(["--home", str(demo), "review", "T-261116", "--reviewers", "codex,claude", "--dry-run"]) == 0
    err = capsys.readouterr().err
    assert "blind review pack" in err

