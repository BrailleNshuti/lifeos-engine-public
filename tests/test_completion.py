import argparse

from lifeos import completion
from lifeos.cli import build_parser, main


def tree():
    p = argparse.ArgumentParser(prog="lifeos")
    p.add_argument("--home")
    sub = p.add_subparsers(dest="cmd")
    a = sub.add_parser("alpha")
    a.add_argument("--dry-run", action="store_true")
    b = sub.add_parser("beta")
    bs = b.add_subparsers(dest="act")
    bs.add_parser("start").add_argument("--days")
    bs.add_parser("end")
    return p


def test_the_tree_lists_commands_subcommands_and_options():
    t = completion.walk(tree())
    assert {"alpha", "beta", "--home"} <= set(t[""]["words"])
    assert "--dry-run" in t["alpha"]["words"]
    assert {"start", "end"} <= set(t["beta"]["words"]) and "--days" in t["beta start"]["words"]


def test_powershell_and_bash_scripts_contain_every_real_command():
    for shell in ("powershell", "bash"):
        script = completion.script(shell, build_parser())
        for cmd in ("ask", "guard", "today", "experiment", "pipeline"):
            assert cmd in script
    assert "Register-ArgumentCompleter" in completion.script("powershell", build_parser())
    assert "complete -F" in completion.script("bash", build_parser())


def test_cli_prints_a_script_and_rejects_unknown_shells(capsys):
    assert main(["completion", "powershell"]) == 0
    assert "Register-ArgumentCompleter" in capsys.readouterr().out
    try:
        main(["completion", "fish"])
    except SystemExit as e:
        assert e.code == 2
