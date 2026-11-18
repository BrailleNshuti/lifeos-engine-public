"""A Windows checkout (CRLF line endings, UTF-8 BOM) must read and verify exactly like a Linux one."""
import json
import shutil

from lifeos import store, verify
from lifeos.cli import main


def convert(path, newline="\r\n", bom=False):
    data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", newline.encode())
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + data)


def test_the_hash_chain_survives_a_crlf_checkout(tmp_path):
    (tmp_path / "logs").mkdir()
    for i in range(5):
        store.append_run_record(tmp_path, {"run_id": f"R-{i:04d}", "command": "canary", "status": "ok", "date": "2026-11-18"})
    head = verify.verify_chain(tmp_path)["head"]
    convert(tmp_path / "logs" / "runs.jsonl")
    res = verify.verify_chain(tmp_path, anchor=head)
    assert res["ok"] and res["records"] == 5 and res["anchor_found"], res


def test_every_command_on_the_demo_home_agrees_after_crlf_and_bom(tmp_path, demo, capsys):
    plain = tmp_path / "plain"
    win = tmp_path / "win"
    shutil.copytree(demo, plain)
    shutil.copytree(demo, win)
    for path in list((win / "logs").glob("*.csv")) + list(win.glob("*.md")):
        convert(path, bom=path.suffix == ".csv")
    outputs = {}
    for name, home in (("plain", plain), ("win", win)):
        for cmd in (["week"], ["timeline", "--weeks", "3"], ["today"], ["savings"], ["calibration"]):
            capsys.readouterr()
            code = main(["--home", str(home)] + cmd)
            outputs[(name, " ".join(cmd))] = (code, capsys.readouterr().out)
    for cmd in ("week", "timeline --weeks 3", "today", "savings", "calibration"):
        a, b = outputs[("plain", cmd)], outputs[("win", cmd)]
        assert a[0] == b[0], cmd
        assert a[1].replace("\r", "") == b[1].replace("\r", ""), cmd
