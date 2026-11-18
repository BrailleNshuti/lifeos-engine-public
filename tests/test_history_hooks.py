import os
import subprocess

import pytest

from lifeos import history, hooks
from lifeos.cli import main

FAKE = "sk-ant-api03-" + "a1B2c3D4" * 5


def git(repo, *args):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env=env)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "a.txt").write_text("hello\n")
    git(tmp_path, "add", "."); git(tmp_path, "commit", "-qm", "one")
    return tmp_path


def test_clean_history_has_no_findings(repo):
    out = history.scan(repo)
    assert out["commits"] == 1 and out["findings"] == []


def test_a_secret_removed_later_is_still_found_and_masked(repo):
    (repo / "a.txt").write_text(f"key = {FAKE}\n")
    git(repo, "commit", "-qam", "oops")
    (repo / "a.txt").write_text("clean\n")
    git(repo, "commit", "-qam", "removed")
    out = history.scan(repo)
    assert len(out["findings"]) == 1
    f = out["findings"][0]
    assert f["file"] == "a.txt" and len(f["commit"]) == 12 and FAKE not in str(out)


def test_cli_history_exit_codes(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    assert main(["history-scan"]) == 0
    (repo / "b.txt").write_text(f"{FAKE}\n")
    git(repo, "add", "."); git(repo, "commit", "-qm", "x")
    assert main(["history-scan"]) == 1
    assert FAKE not in capsys.readouterr().out


def test_hook_install_and_no_silent_overwrite(repo):
    path = hooks.install(repo)
    assert path.name == "pre-commit" and "lifeos guard --staged" in path.read_text()
    assert hooks.install(repo) == path  # reinstalling our own hook is harmless
    path.write_text("#!/bin/sh\necho mine\n")
    with pytest.raises(hooks.HookError):
        hooks.install(repo)
    hooks.install(repo, force=True)
    assert "lifeos guard --staged" in path.read_text()


def test_hook_needs_a_git_repo(tmp_path):
    with pytest.raises(hooks.HookError):
        hooks.install(tmp_path)
