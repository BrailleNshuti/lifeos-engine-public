"""Seeded garbage in every log file: read-only commands must answer or fail politely, never raise a traceback."""
import contextlib
import io
import random
import shutil

import pytest

from lifeos.cli import main

LOGS = ["ledger.csv", "proofs.csv", "ratings.csv", "predictions.csv", "vocab.csv", "experiments.csv", "runs.jsonl"]
COMMANDS = [["week"], ["seats"], ["runs"], ["verify"], ["savings"], ["numbers", "--out", "{o}"], ["calibration"], ["learn"],
            ["mistakes"], ["vocab", "quiz"], ["experiment", "list"], ["digest"], ["kaizen"], ["decide", "list"],
            ["prove", "--skip-tests"], ["hours"], ["health"], ["cockpit"]]


def garbage(rng, header):
    pieces = [header, "﻿" + header, "", "\x00\x00", ",,,,,,", "a,b", '"unterminated,quote', "2026-13-45,x,y,z,w",
              "{", '{"command": "ask"', "[1,2,3]", "null", "x" * 5000, "ü,ö,ä,日本語", "1e999,nan,inf",
              '{"command":"ask","tokens":"many","status":null,"date":5}', "2026-11-01,T,claude,notanumber,"]
    lines = [rng.choice(pieces) for _ in range(rng.randint(1, 12))]
    return rng.choice(["\n", "\r\n"]).join(lines) + rng.choice(["", "\n", "\r\n", "\n\n"])


@pytest.mark.parametrize("seed", range(8))
def test_read_commands_survive_garbage_logs(seed, tmp_path, demo):
    home = tmp_path / "home"
    shutil.copytree(demo, home)
    rng = random.Random(seed)
    for name in LOGS:
        target = home / "logs" / name
        target.parent.mkdir(exist_ok=True)
        header = "date,task,model,score,kind,note" if name.endswith(".csv") else ""
        target.write_text(garbage(rng, header), encoding="utf-8", newline="")
    failures = []
    for cmd in COMMANDS:
        argv = ["--home", str(home)] + [c.replace("{o}", str(tmp_path / f"o{seed}.html")) for c in cmd]
        sink = io.StringIO()
        try:
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                code = main(argv)
        except SystemExit as exit_:
            code = exit_.code if isinstance(exit_.code, int) else 1
        except Exception as err:  # the point of the test
            failures.append(f"{' '.join(cmd)}: {type(err).__name__}: {err}")
            continue
        if code not in (0, 1, 2):
            failures.append(f"{' '.join(cmd)}: exit {code}")
    assert not failures, "\n".join(failures)


def test_read_csv_rows_skips_short_long_and_bad_rows(tmp_path):
    from lifeos.store import read_csv_rows
    f = tmp_path / "x.csv"
    f.write_bytes(b"\xef\xbb\xbfid,kind,value\nA,predict,5\nshort\nB,predict,1,extra\nC,,9\nD,resolve,\xff\n")
    assert [r["id"] for r in read_csv_rows(f, ("id", "kind"))] == ["A", "D"]
    assert read_csv_rows(tmp_path / "missing.csv") == []


def test_nul_bytes_never_reach_the_csv_parser(tmp_path):
    from lifeos.store import read_csv_rows
    f = tmp_path / "n.csv"
    f.write_bytes(b"id,kind\nA,x\n\x00\x00\nB\x00,y\n")
    assert [r["id"] for r in read_csv_rows(f, ("id",))] == ["A", "B"]
