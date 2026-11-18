"""Attack the ledger: seeded random tampering must always be caught, and the known limits must behave as documented."""
import datetime as dt
import json
import random
import shutil

import pytest

from lifeos import ask
from lifeos.verify import verify_chain

D = dt.date(2026, 12, 1)
N = 6


@pytest.fixture
def chain(tmp_path, demo):
    home = tmp_path / "home"
    shutil.copytree(demo, home)
    for _ in range(N):
        ask.run_ask(home, "claude", "T-261116", adapters={"claude": lambda p: "ok"}, today=D)
    log = home / "logs" / "runs.jsonl"
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == N and verify_chain(home)["ok"]
    return home, log, lines, verify_chain(home)["head"]


def write(log, lines):
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.mark.parametrize("seed", range(25))
def test_editing_any_field_of_a_non_final_record_is_caught(chain, seed):
    home, log, lines, _ = chain
    rng = random.Random(seed)
    i = rng.randrange(N - 1)
    rec = json.loads(lines[i])
    key = rng.choice([k for k in rec if k != "prev_hash"])
    rec[key] = "tampered" if rec[key] != "tampered" else "other"
    lines[i] = json.dumps(rec)
    write(log, lines)
    assert not verify_chain(home)["ok"]


@pytest.mark.parametrize("seed", range(15))
def test_deleting_a_non_final_record_is_caught(chain, seed):
    home, log, lines, _ = chain
    del lines[random.Random(seed).randrange(N - 1)]
    write(log, lines)
    assert not verify_chain(home)["ok"]


@pytest.mark.parametrize("seed", range(15))
def test_swapping_two_records_is_caught(chain, seed):
    home, log, lines, _ = chain
    a, b = random.Random(seed).sample(range(N), 2)
    lines[a], lines[b] = lines[b], lines[a]
    write(log, lines)
    assert not verify_chain(home)["ok"]


@pytest.mark.parametrize("seed", range(10))
def test_inserting_a_forged_record_is_caught(chain, seed):
    home, log, lines, _ = chain
    i = random.Random(seed).randrange(1, N)
    forged = json.loads(lines[i])
    forged["run_id"] = "R-forged"
    lines.insert(i, json.dumps(forged))
    write(log, lines)
    assert not verify_chain(home)["ok"]


def test_duplicating_a_record_is_caught(chain):
    home, log, lines, _ = chain
    lines.insert(2, lines[2])
    write(log, lines)
    assert not verify_chain(home)["ok"]


def test_a_torn_record_is_reported(chain):
    home, log, lines, _ = chain
    log.write_text("\n".join(lines[:-1] + [lines[-1][:30]]) + "\n", encoding="utf-8")
    assert verify_chain(home)["errors"]


# ---- the documented limits: the chain alone cannot see these, the saved head hash (the anchor) can ----

def test_cutting_the_tail_passes_the_chain_but_not_the_anchor(chain):
    home, log, lines, head = chain
    write(log, lines[:-1])
    assert verify_chain(home)["ok"]
    assert verify_chain(home, anchor=head)["anchor_found"] is False


def test_rewriting_the_last_record_passes_the_chain_but_not_the_anchor(chain):
    home, log, lines, head = chain
    rec = json.loads(lines[-1])
    rec["status"] = "failed"
    write(log, lines[:-1] + [json.dumps(rec)])
    assert verify_chain(home)["ok"]
    assert verify_chain(home, anchor=head)["anchor_found"] is False


def test_the_untouched_log_matches_its_anchor(chain):
    home, _, _, head = chain
    assert verify_chain(home, anchor=head)["anchor_found"] is True


def test_crlf_conversion_is_not_an_attack(chain):
    home, log, _, head = chain
    log.write_bytes(log.read_bytes().replace(b"\n", b"\r\n"))
    out = verify_chain(home, anchor=head)
    assert out["ok"] and out["anchor_found"] is True
