"""lifeos debate: blind answers, then objections and defences; rules score the evidence, never the votes."""
import datetime as dt
import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from lifeos import ask, debate, seats
from lifeos.cli import main
from lifeos.store import read_run_records

TODAY = dt.date(2026, 11, 20)
SEATS = ["claude", "codex", "gemini"]
QUESTION = "Should the made-up store keep its data in sqlite or in plain json files?"
ANSWERS = {
    "claude": "1. The store should be sqlite.\n2. Tests come first.\n3. The call cap is 14.",
    "codex": "1. The store should be json files.\n2. Tests come first.\n3. The call cap is 24.",
    "gemini": "1. The store should be sqlite.\n2. Docs can wait.\n3. The call cap is 24.",
}
OWN = {"claude": "The call cap is 14.", "codex": "The store should be json files.", "gemini": "Docs can wait."}
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def begin(home, seed="seed-1", seats_=SEATS, question=QUESTION):
    return debate.start(home, question, seats_, seed=seed, today=TODAY)


def put(home, tmp_path, did, rnd, seat, text):
    f = tmp_path / f"{rnd}-{seat}.txt"
    f.write_text(text, encoding="utf-8")
    return debate.record(home, did, rnd, seat, f, today=TODAY)


def round_one(home, tmp_path, did, answers=ANSWERS):
    for seat, text in answers.items():
        put(home, tmp_path, did, 1, seat, text)


def labels(meta):
    return {seat: label for label, seat in meta["labels"].items()}


def objection(target, claim, evidence="", kind="evidence", settle=""):
    lines = ["OBJECTION", f"target: {target}", f"claim: {claim}", f"evidence: {evidence}", f"kind: {kind}"]
    return "\n".join(lines + ([f"settle: {settle}"] if settle else []) + ["END"])


def defence(obj, response, evidence="", settle="", revised="the claim now reads differently"):
    lines = ["DEFENCE", f"objection: {obj}", f"response: {response}", f"evidence: {evidence}"]
    if response == "revise" and revised:
        lines.append(f"revised: {revised}")
    return "\n".join(lines + ([f"settle: {settle}"] if settle else []) + ["END"])


def two_seat(home, tmp_path, objections, defences=None, seats_=("claude", "codex")):
    """A two-seat debate: codex raises `objections` (built from claude's label) and claude answers with `defences`."""
    meta = begin(home, seats_=list(seats_))
    did, lab = meta["id"], labels(meta)
    put(home, tmp_path, did, 1, "claude", ANSWERS["claude"])
    put(home, tmp_path, did, 1, "codex", ANSWERS["codex"])
    put(home, tmp_path, did, 2, "codex", "\n".join(objections(lab["claude"])))
    put(home, tmp_path, did, 2, "claude", "nothing to add here")
    if defences:
        put(home, tmp_path, did, 3, "claude", "\n".join(defences(debate.objections_against(home, did, "claude"))))
    return meta, did, lab


# ---------------------------------------------------------------- start

def test_start_stores_question_seed_labels_and_a_pack_hash(home):
    meta = begin(home)
    folder = home / "debates" / meta["id"]
    stored = json.loads((folder / "debate.json").read_text(encoding="utf-8"))
    assert stored["question"] == QUESTION and stored["seats"] == SEATS and stored["seed"] == "seed-1"
    assert sorted(stored["labels"]) == ["A", "B", "C"] and sorted(stored["labels"].values()) == sorted(SEATS)
    pack = (folder / "prompts" / "r1.txt").read_text(encoding="utf-8")
    assert stored["pack_sha256"] == hashlib.sha256(pack.encode("utf-8")).hexdigest()


def test_the_shuffle_is_seeded_and_reproducible(home):
    a, b = begin(home, seed="same"), begin(home, seed="same")
    assert a["labels"] == b["labels"] == debate.make_labels(SEATS, "same")
    mappings = {tuple(sorted(debate.make_labels(SEATS, f"s{i}").items())) for i in range(30)}
    assert len(mappings) > 1  # the seed really changes the order


@pytest.mark.parametrize("bad", [["claude"], ["claude", "claude"], ["claude", "nobody"], list("abcde")])
def test_start_needs_two_to_four_known_distinct_seats(home, bad):
    with pytest.raises(debate.DebateError):
        begin(home, seats_=bad)


def test_start_refuses_a_question_that_names_a_seat_or_holds_a_secret(home):
    with pytest.raises(debate.DebateError, match="names a seat"):
        begin(home, question="Is Codex better than the others at tests?")
    with pytest.raises(ask.Blocked):
        begin(home, question="Use key sk-ant-api03-" + "a1B2c3D4" * 5 + " for this?")


def test_ids_are_checked_so_a_path_cannot_escape(home):
    with pytest.raises(debate.DebateError):
        debate.load(home, "../tasks")


# ---------------------------------------------------------------- round 1 and record

def test_round_one_gives_every_seat_the_identical_pack_with_no_names(home):
    meta = begin(home)
    out = debate.next_round(home, meta["id"])
    assert out["round"] == 1 and set(out["prompts"]) == set(SEATS)
    assert len(set(out["prompts"].values())) == 1
    prompt = out["prompts"]["claude"]
    assert QUESTION in prompt and not any(s in prompt.lower() for s in SEATS)
    assert hashlib.sha256(prompt.encode("utf-8")).hexdigest() == meta["pack_sha256"]


def test_record_stores_the_answer_with_its_hash_and_a_chained_ledger_record(home, tmp_path, capsys):
    did = begin(home)["id"]
    out = put(home, tmp_path, did, 1, "codex", ANSWERS["codex"])
    stored = home / "debates" / did / "r1-codex.md"
    assert hashlib.sha256(stored.read_bytes()).hexdigest() == out["sha256"]
    rec = [r for r in read_run_records(home) if r.get("command") == "debate"][-1]
    assert rec["debate_id"] == did and rec["round"] == 1 and rec["model"] == "codex"
    assert rec["answer_sha256"] == out["sha256"] and rec["status"] == "ok" and rec["prev_hash"]
    assert main(["--home", str(home), "verify"]) == 0


def test_record_never_overwrites_and_resumes_a_half_written_one(home, tmp_path):
    did = begin(home)["id"]
    put(home, tmp_path, did, 1, "codex", ANSWERS["codex"])
    with pytest.raises(debate.DebateError, match="already recorded"):
        put(home, tmp_path, did, 1, "codex", "a different answer with more words")
    # a crash between the file and the ledger leaves the file only: the same file finishes the job
    (home / "debates" / did / "r1-gemini.md").write_text(ANSWERS["gemini"], encoding="utf-8")
    put(home, tmp_path, did, 1, "gemini", ANSWERS["gemini"])
    assert sum(r.get("command") == "debate" and r.get("round") == 1 for r in read_run_records(home)) == 2


def test_record_checks_seat_round_size_secrets_and_the_ledger(home, tmp_path):
    did = begin(home)["id"]
    with pytest.raises(debate.DebateError):
        put(home, tmp_path, did, 1, "grok", "x y z w")
    with pytest.raises(debate.DebateError):
        put(home, tmp_path, did, 4, "codex", "x y z w")
    with pytest.raises(ask.Blocked):
        put(home, tmp_path, did, 1, "codex", "my key sk-ant-api03-" + "a1B2c3D4" * 5)
    assert not (home / "debates" / did / "r1-codex.md").exists()
    shutil.rmtree(home / "logs")
    with pytest.raises(debate.DebateError, match="ledger"):
        put(home, tmp_path, did, 1, "codex", ANSWERS["codex"])


def test_next_waits_for_the_previous_round_unless_told_to_skip(home, tmp_path):
    did = begin(home)["id"]
    put(home, tmp_path, did, 1, "claude", ANSWERS["claude"])
    out = debate.next_round(home, did, rnd=2)
    assert out["prompts"] == {} and set(out["waiting"]) == {"codex", "gemini"}
    put(home, tmp_path, did, 1, "codex", ANSWERS["codex"])
    out = debate.next_round(home, did, rnd=2, skip_missing=True)
    assert set(out["prompts"]) == {"claude", "codex"}


# ---------------------------------------------------------------- round 2: blind, relabeled

def test_round_two_shows_only_the_others_relabeled_and_never_names_or_hashes(home, tmp_path):
    meta = begin(home)
    did, lab = meta["id"], labels(meta)
    round_one(home, tmp_path, did)
    out = debate.next_round(home, did)
    assert out["round"] == 2
    hashes = [r["answer_sha256"] for r in read_run_records(home) if r.get("answer_sha256")] + [meta["pack_sha256"]]
    assert len(hashes) == 4
    for seat, prompt in out["prompts"].items():
        others = [s for s in SEATS if s != seat]
        assert not any(name in prompt.lower() for name in SEATS), "a seat name leaked"
        assert not any(h in prompt for h in hashes), "a hash leaked"
        assert all(f"ANSWER {lab[o]}" in prompt for o in others)
        assert f"ANSWER {lab[seat]}" not in prompt
        assert OWN[seat] not in prompt  # its own answer is not shown back


def test_round_two_order_follows_the_stored_seed(home, tmp_path):
    a, b = begin(home, seed="x1"), begin(home, seed="x1")
    for m in (a, b):
        round_one(home, tmp_path, m["id"])
    pa, pb = debate.next_round(home, a["id"])["prompts"], debate.next_round(home, b["id"])["prompts"]
    assert pa == pb  # same seed, same relabeling: replayable


def test_a_name_inside_an_answer_is_scrubbed_before_others_see_it(home, tmp_path):
    meta = begin(home)
    answers = dict(ANSWERS, claude="1. As Claude and Anthropic say, sqlite wins.\n2. Hash " + "ab" * 32 + " is stable.")
    round_one(home, tmp_path, meta["id"], answers)
    shown = debate.next_round(home, meta["id"])["prompts"]["codex"]
    assert "claude" not in shown.lower() and "anthropic" not in shown.lower() and "ab" * 32 not in shown


# ---------------------------------------------------------------- parsing rules

def test_an_objection_without_evidence_is_only_an_opinion():
    text = "\n".join([objection("B2", "wrong", evidence="none"), objection("B1", "wrong", evidence="because it is"),
                       objection("B3", "wrong", evidence="seats.py sets CALL_CAP = 24 on line 19", kind="opinion"),
                       objection("C3", "wrong", evidence="seats.py sets CALL_CAP = 24 on line 19")])
    kinds = [o["counts"] for o in debate.parse_objections(text)]
    assert kinds == [False, False, False, True]


def test_parsing_survives_markdown_noise_and_ignores_prose():
    text = ("Here are my points.\n**OBJECTION**\n- target: `B2`\n- claim: the cap is 24\n- evidence: README says a 24-call cap\n"
            "- kind: evidence\nEND\nthanks")
    got = debate.parse_objections(text)
    assert len(got) == 1 and got[0]["target"] == "B2" and got[0]["counts"]


def test_objections_that_point_nowhere_do_not_use_up_the_cap_of_three(home, tmp_path):
    ev = "seats.py line 19 sets CALL_CAP = 24"
    meta, did, lab = two_seat(home, tmp_path, lambda c: [objection(f"{c}99", f"nowhere {i}", ev) for i in range(3)]
                              + [objection(f"{c}1", "a real one", ev)])
    rep = debate.score(home, did)
    assert rep["ignored"] == 3 and [(c["target"], c["objections"]) for c in rep["challenged"]] == [(f"{lab['claude']}1", 1)]


def test_a_revision_shows_what_the_claim_now_says(home, tmp_path):
    ev = "seats.py line 19 sets CALL_CAP = 24"
    meta, did, lab = two_seat(
        home, tmp_path, lambda c: [objection(f"{c}3", "the cap is 24", ev)],
        lambda objs: [defence(objs[0]["id"], "revise", "tests/test_cap.py::test_cap_is_24 passes", revised="The call cap is 24.")])
    row = debate.score(home, did)["challenged"][0]
    assert row["verdict"] == "SURVIVED" and 'revised to "The call cap is 24."' in row["why"]
    assert "read the revision" in debate.render_score(debate.score(home, did))


def test_an_objection_needs_target_claim_explicit_kind_and_evidence_to_count():
    ev = "seats.py line 19 sets CALL_CAP = 24"
    text = "\n".join(["OBJECTION\ntarget: B1\nevidence: " + ev + "\nEND",                        # no claim, no kind
                      "OBJECTION\ntarget: B1\nclaim: wrong\nevidence: " + ev + "\nEND",          # no kind
                      "OBJECTION\nclaim: wrong\nevidence: " + ev + "\nkind: evidence\nEND",      # no target
                      "OBJECTION\ntarget: B1\nclaim: wrong\nevidence: " + ev + "\nkind: evidenceXYZ\nEND",  # not exactly evidence
                      "OBJECTION\ntarget: B1\nclaim: wrong\nevidence: " + ev + "\nkind: evidence\nEND"])
    assert [o["counts"] for o in debate.parse_objections(text)] == [False, False, False, False, True]


@pytest.mark.parametrize("text, ok", [
    ("lifeos/debate.py:42", True), ("https://example.com/spec", True), ("test_a::test_b", True),
    ("pytest tests/test_x.py", True), ("ran git status", True), ("debate.json", True),
    ("the readme says 24 calls", True),
    ("trust me on this", False), ("it is obviously wrong", False), ("because it is", False), ("lots of 24", False),
    ("none", False), ("", False), ("n/a", False)])
def test_the_evidence_gate_wants_a_pointer(text, ok):
    assert debate.has_evidence(text) is ok


def test_a_rebuttal_without_evidence_counts_as_a_concession():
    text = "\n".join([defence("O1", "rebut", ""), defence("O2", "rebut", "the test in tests/test_x.py::test_y fails"),
                      defence("O3", "revise", ""), defence("O4", "revise", "see rules.md line 4")])
    assert [d["response"] for d in debate.parse_defences(text)] == ["concede", "rebut", "concede", "revise"]


# ---------------------------------------------------------------- scoring

def scored_debate(home, tmp_path):
    """Seat A..C objections and defences covering every verdict. Returns (meta, report)."""
    meta = begin(home)
    did, lab = meta["id"], labels(meta)
    round_one(home, tmp_path, did)
    ev = "seats.py line 19 sets CALL_CAP = 24 and the README says 24 calls"
    # codex attacks claude's claim 3 (evidence, will be rebutted with evidence -> OPEN)
    # gemini attacks claude's claim 1 (evidence, will be conceded -> FELL)
    # gemini opinion on claude's claim 2 (no evidence -> set aside, claim stays unchallenged)
    put(home, tmp_path, did, 2, "codex", "\n".join([
        objection(f"{lab['claude']}3", "the cap is 24 not 14", ev, settle="grep CALL_CAP lifeos/seats.py"),
        objection(f"{lab['gemini']}2", "docs are part of done", "rule 4 says a command change updates the README"),
        objection(f"{lab['gemini']}1", "sqlite breaks stdlib-only? no", "")]))
    put(home, tmp_path, did, 2, "gemini", "\n".join([
        objection(f"{lab['claude']}1", "json is simpler to diff", "docs/LOGS.md says every log is plain text you can read"),
        objection(f"{lab['claude']}2", "feels wrong", ""),
        objection(f"{lab['codex']}1", "the store must be json", "CHANGELOG 0.4.0 says store writes are atomic json lines")]))
    put(home, tmp_path, did, 2, "claude", "\n".join([
        objection(f"{lab['codex']}3", "cap is 14", "I remember it from the readme")]))
    return meta, did, lab


def test_every_verdict_is_rule_based(home, tmp_path):
    meta, did, lab = scored_debate(home, tmp_path)
    rep = debate.score(home, did)
    by = {c["target"]: c for c in rep["challenged"]}
    # nothing answered yet: every counted objection is unanswered, so it fell
    assert all(c["verdict"] == "FELL" for c in rep["challenged"])
    assert rep["opinion_set_aside"] == 3 and rep["unchallenged"] >= 1
    assert f"{lab['claude']}2" not in by  # an opinion alone never challenges a claim


def test_the_seat_scorecard_is_in_the_report_and_only_shown_with_reveal(home, tmp_path, capsys):
    meta, did, lab = scored_debate(home, tmp_path)
    card = debate.score(home, did)["seats"]
    assert (card["codex"]["raised"], card["codex"]["counted"], card["codex"]["landed"]) == (3, 2, 2)
    assert (card["gemini"]["raised"], card["gemini"]["counted"], card["gemini"]["landed"]) == (3, 2, 2)
    assert (card["claude"]["raised"], card["claude"]["counted"]) == (1, 0)
    assert (card["claude"]["fell"], card["claude"]["unchallenged"], card["claude"]["unanswered"]) == (2, 1, 2)
    assert main(["--home", str(home), "debate", "score", did]) == 0
    assert "landed" not in capsys.readouterr().out
    assert main(["--home", str(home), "debate", "score", did, "--reveal"]) == 0
    shown = capsys.readouterr().out
    assert "landed" in shown and "codex" in shown
    assert main(["--home", str(home), "debate", "score", did, "--json"]) == 0
    assert "landed" not in capsys.readouterr().out


def test_survived_open_and_fell_after_the_defences(home, tmp_path):
    meta, did, lab = scored_debate(home, tmp_path)
    c, x = lab["claude"], lab["codex"]
    # claude defends: rebut with evidence the codex objection; concede the gemini one
    mine = {o["target"]: o["id"] for o in debate.objections_against(home, did, "claude")}
    put(home, tmp_path, did, 3, "claude", "\n".join([
        defence(mine[f"{c}3"], "rebut", "tests/test_cap.py::test_cap_is_14 passes on main", settle="pytest tests/test_cap.py"),
        defence(mine[f"{c}1"], "concede")]))
    rep = debate.score(home, did)
    by = {r["target"]: r for r in rep["challenged"]}
    assert by[f"{c}3"]["verdict"] == "OPEN" and "grep CALL_CAP" in " ".join(by[f"{c}3"]["settle"])
    assert by[f"{c}1"]["verdict"] == "FELL"
    # codex's claim 1 was attacked by gemini and codex never answered: FELL (unanswered)
    assert by[f"{x}1"]["verdict"] == "FELL" and "unanswered" in by[f"{x}1"]["why"]


def test_revise_with_evidence_survives(home, tmp_path):
    meta, did, lab = scored_debate(home, tmp_path)
    g = lab["gemini"]
    mine = {o["target"]: o["id"] for o in debate.objections_against(home, did, "gemini")}
    assert list(mine) == [f"{g}2"]  # the empty-evidence objection against claim 1 is an opinion and has no id
    put(home, tmp_path, did, 3, "gemini", defence(mine[f"{g}2"], "revise", "rule 4 in rules.md: README rows are part of done"))
    by = {r["target"]: r for r in debate.score(home, did)["challenged"]}
    assert by[f"{g}2"]["verdict"] == "SURVIVED"


def test_every_claim_gets_a_verdict_and_an_unchallenged_one_says_so(home, tmp_path):
    meta = begin(home)
    round_one(home, tmp_path, meta["id"])
    rep = debate.score(home, meta["id"])
    assert rep["challenged"] == [] and rep["unchallenged"] == 9 and len(rep["claims"]) == 9
    assert {c["verdict"] for c in rep["claims"]} == {"SURVIVED"}
    text = debate.render_score(rep)
    assert text.count("SURVIVED") >= 9 and "unchallenged (not verified)" in text and "not that it is true" in text


def test_a_whole_answer_objection_covers_its_claims_instead_of_leaving_them_unchallenged(home, tmp_path):
    ev = "seats.py line 19 sets CALL_CAP = 24 for every seat"
    meta, did, lab = two_seat(home, tmp_path, lambda c: [objection(c, "the whole approach is wrong", ev)])
    rep = debate.score(home, did)
    c = lab["claude"]
    assert [r["target"] for r in rep["claims"] if r["target"].startswith(c)] == [f"{c}*"]
    whole = next(r for r in rep["claims"] if r["target"] == f"{c}*")
    assert whole["verdict"] == "FELL" and "unanswered" in whole["why"]
    assert rep["unchallenged"] == 3  # only codex's own three claims remain unchallenged


def test_more_than_three_objections_per_answer_are_reported_as_ignored(home, tmp_path):
    ev = "seats.py line 19 sets CALL_CAP = 24"
    meta, did, lab = two_seat(home, tmp_path, lambda c: [objection(f"{c}1", f"point {i}", ev) for i in range(5)])
    rep = debate.score(home, did)
    assert rep["ignored"] == 2 and rep["challenged"][0]["objections"] == 3


def test_open_without_a_settle_test_names_the_two_pieces_of_evidence_to_compare(home, tmp_path):
    meta, did, lab = two_seat(
        home, tmp_path,
        lambda c: [objection(f"{c}3", "the cap is 24", "seats.py line 19 sets CALL_CAP = 24")],
        lambda objs: [defence(objs[0]["id"], "rebut", "tests/test_cap.py::test_cap_is_14 passes")])
    row = debate.score(home, did)["challenged"][0]
    assert row["verdict"] == "OPEN"
    assert row["settle"][0].startswith("no settling test was proposed; check both pieces of evidence")
    assert "CALL_CAP = 24" in row["settle"][0] and "test_cap_is_14" in row["settle"][0]


def test_a_revision_must_say_what_the_claim_now_is():
    text = defence("O1", "revise", "see rules.md line 4", revised="") + "\n" + defence("O2", "revise", "see rules.md line 4")
    assert [d["response"] for d in debate.parse_defences(text)] == ["concede", "revise"]


def test_agreement_is_logged_but_never_changes_a_verdict(home, tmp_path, monkeypatch):
    meta, did, lab = scored_debate(home, tmp_path)
    rep = debate.score(home, did)
    assert "logged, not used" in debate.render_score(rep) and rep["agreement_logged"] >= 1
    verdicts = [(c["target"], c["verdict"]) for c in rep["challenged"]]
    for fake in (0, 99):  # whatever the agreement count is, the verdicts stay the same
        monkeypatch.setattr(debate, "agreement", lambda answers, n=fake: n)
        again = debate.score(home, did)
        assert again["agreement_logged"] == fake
        assert verdicts == [(c["target"], c["verdict"]) for c in again["challenged"]]


def test_score_refuses_an_answer_file_changed_after_it_was_recorded(home, tmp_path):
    meta = begin(home)
    round_one(home, tmp_path, meta["id"])
    target = home / "debates" / meta["id"] / "r1-codex.md"
    target.write_text(target.read_text(encoding="utf-8") + "\n4. Sneaky extra claim added later.", encoding="utf-8")
    with pytest.raises(debate.DebateError, match="changed after"):
        debate.score(home, meta["id"])


def test_score_hides_seat_names_unless_asked(home, tmp_path):
    meta, did, lab = scored_debate(home, tmp_path)
    rep = debate.score(home, did)
    assert not any(s in debate.render_score(rep).lower() for s in SEATS)
    assert all(s in debate.render_score(rep, reveal=True).lower() for s in SEATS)


# ---------------------------------------------------------------- round 3 prompt

def test_round_three_shows_only_objections_against_that_seat_without_authors(home, tmp_path):
    meta, did, lab = scored_debate(home, tmp_path)
    out = debate.next_round(home, did, skip_missing=True)
    assert out["round"] == 3
    prompt = out["prompts"]["claude"]
    assert "the cap is 24 not 14" in prompt and "json is simpler to diff" in prompt
    assert "feels wrong" not in prompt and "opinion" in prompt.lower()  # opinions are set aside but counted
    assert not any(s in prompt.lower() for s in SEATS)
    assert "remember it from the readme" not in prompt  # nothing aimed at others
    assert "your claim 3" in prompt and not re.search(r"\b[A-D][1-9*]\b", prompt), "the defender's own label leaked"


# ---------------------------------------------------------------- integrity

def test_a_swapped_label_mapping_is_caught_because_its_hash_is_in_the_ledger(home, tmp_path):
    meta, did, lab = scored_debate(home, tmp_path)
    path = home / "debates" / did / "debate.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    a, b = list(stored["labels"])[:2]
    stored["labels"][a], stored["labels"][b] = stored["labels"][b], stored["labels"][a]
    path.write_text(json.dumps(stored), encoding="utf-8")
    with pytest.raises(debate.DebateError, match="changed after"):
        debate.score(home, did)
    with pytest.raises(debate.DebateError, match="changed after"):
        debate.next_round(home, did)


def test_a_changed_round_one_pack_is_caught(home):
    did = begin(home)["id"]
    (home / "debates" / did / "prompts" / "r1.txt").write_text("a different question entirely", encoding="utf-8")
    with pytest.raises(debate.DebateError, match=r"r1\.txt"):
        debate.load(home, did)


def test_score_refuses_a_broken_ledger_chain(home, tmp_path):
    meta, did, lab = scored_debate(home, tmp_path)
    runs = home / "logs" / "runs.jsonl"
    lines = runs.read_bytes().split(b"\n")
    lines[2], lines[3] = lines[3], lines[2]  # reorder two records after the start record
    runs.write_bytes(b"\n".join(lines))
    for step in (lambda: debate.score(home, did), lambda: debate.next_round(home, did),
                 lambda: debate.run(home, did, execute=True, adapters={s: Scripted("x") for s in SEATS}, today=TODAY)):
        with pytest.raises(debate.DebateError, match="chain is broken"):
            step()


def test_score_json_is_scrubbed_like_the_table(home, tmp_path, capsys):
    meta, did, lab = two_seat(
        home, tmp_path,
        lambda c: [objection(f"{c}3", "the cap is 24", "seats.py line 19 sets CALL_CAP = 24", settle="ask Claude to run pytest -q")],
        lambda objs: [defence(objs[0]["id"], "rebut", "tests/test_cap.py::test_cap_is_14 passes", settle="ask Codex to rerun it")])
    assert main(["--home", str(home), "debate", "score", did, "--json"]) == 0
    out = capsys.readouterr().out.lower()
    assert "settle" in out and not any(s in out for s in SEATS)
    assert main(["--home", str(home), "debate", "score", did, "--json", "--reveal"]) == 0
    assert "claude" in capsys.readouterr().out.lower()


def test_parallel_records_keep_the_ledger_chain_valid(home, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    did = begin(home)["id"]
    files = {}
    for seat in SEATS:
        files[seat] = tmp_path / f"{seat}.txt"
        files[seat].write_text(ANSWERS[seat], encoding="utf-8")
    with ThreadPoolExecutor(3) as pool:
        list(pool.map(lambda s: debate.record(home, did, 1, s, files[s], today=TODAY), SEATS))
    assert main(["--home", str(home), "verify"]) == 0
    assert sum(r.get("round") == 1 for r in read_run_records(home) if r.get("command") == "debate") == 3


def test_a_crlf_checkout_of_the_answers_still_scores(home, tmp_path):
    did = begin(home)["id"]
    f = tmp_path / "crlf.txt"
    f.write_bytes(ANSWERS["claude"].replace("\n", "\r\n").encode("utf-8"))
    debate.record(home, did, 1, "claude", f, today=TODAY)
    put(home, tmp_path, did, 1, "codex", ANSWERS["codex"])
    for stored in (home / "debates" / did).glob("r1-*.md"):  # a Windows checkout rewrites every line ending
        stored.write_bytes(stored.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert debate.score(home, did)["claims_total"] == 6


# ---------------------------------------------------------------- run

class Scripted:
    def __init__(self, text):
        self.text, self.prompts = text, []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.text(prompt) if callable(self.text) else self.text


def test_run_is_a_dry_run_unless_told_otherwise(home):
    did = begin(home)["id"]
    fakes = {s: Scripted("x") for s in SEATS}
    rows = debate.run(home, did, execute=False, adapters=fakes, today=TODAY)
    assert all(r["status"] == "planned" for r in rows) and not any(f.prompts for f in fakes.values())
    assert not [r for r in read_run_records(home) if r.get("command") == "debate" and r.get("round")]  # only `start` is there


def test_run_walks_three_rounds_and_skips_a_seat_that_is_down(home):
    meta = begin(home)
    did, lab = meta["id"], labels(meta)

    def codex(prompt):
        if "ROUND 1" in prompt:
            return ANSWERS["codex"]
        if "ROUND 2" in prompt:
            return objection(f"{lab['claude']}3", "cap", "seats.py line 19 sets CALL_CAP = 24 here")
        return "no objections"

    def claude(prompt):
        if "ROUND 1" in prompt:
            return ANSWERS["claude"]
        if "ROUND 2" in prompt:
            return "nothing to add"
        ids = re.findall(r"^\[(O\d+)\]", prompt, re.M)
        return defence(ids[0], "rebut", "tests/test_cap.py::test_cap_is_14 passes on main") if ids else "none"

    fakes = {"claude": Scripted(claude), "codex": Scripted(codex)}  # gemini has no tool on this machine
    rows = debate.run(home, did, execute=True, adapters=fakes, today=TODAY)
    assert any(r["seat"] == "gemini" and r["status"] == "skipped" and "not available" in r["note"] for r in rows)
    assert {r["status"] for r in rows if r["seat"] != "gemini"} <= {"ok", "idle"}
    rep = debate.score(home, did)
    assert any(c["verdict"] == "OPEN" for c in rep["challenged"])
    assert main(["--home", str(home), "verify"]) == 0
    for f in fakes.values():  # every prompt that left the building was blind
        assert not any("gemini" in p.lower() for p in f.prompts)


def test_run_rests_a_seat_that_hit_a_usage_limit_and_records_the_failure(home):
    did = begin(home)["id"]

    def limited(prompt):
        raise ask.AskError("You have hit your usage limit. Try again in 90 minutes.")

    fakes = {"claude": Scripted(ANSWERS["claude"]), "codex": Scripted(limited), "gemini": Scripted(ANSWERS["gemini"])}
    rows = debate.run(home, did, execute=True, adapters=fakes, today=dt.date.today(), rounds=1)
    assert [r["status"] for r in rows if r["seat"] == "codex"] == ["failed"]
    now = dt.datetime.now(dt.timezone.utc)
    assert "codex" in seats.pressure(read_run_records(home), now)  # debate spend and rests are seen by the budget


def test_a_timeout_is_recorded_as_a_timeout(home):
    did = begin(home)["id"]

    def slow(prompt):
        raise ask.AskError("claude did not answer within 600 s (timed out)")

    rows = debate.run(home, did, execute=True, adapters={"claude": Scripted(slow), "codex": Scripted(ANSWERS["codex"])},
                      today=TODAY, rounds=1)
    assert [r["status"] for r in rows if r["seat"] == "claude"] == ["failed"]
    assert [r["status"] for r in read_run_records(home) if r.get("model") == "claude"] == ["timeout"]


def test_run_never_stores_or_forwards_a_blocked_answer(home):
    did = begin(home)["id"]
    leak = "1. The key is sk-ant-api03-" + "a1B2c3D4" * 5 + " today."
    fakes = {"claude": Scripted(leak), "codex": Scripted(ANSWERS["codex"])}
    rows = debate.run(home, did, execute=True, adapters=fakes, today=TODAY, rounds=1)
    assert [r["status"] for r in rows if r["seat"] == "claude"] == ["blocked"]
    assert not (home / "debates" / did / "r1-claude.md").exists()


def test_run_needs_two_answers_to_continue(home):
    did = begin(home)["id"]
    fakes = {"claude": Scripted(ANSWERS["claude"])}
    rows = debate.run(home, did, execute=True, adapters=fakes, today=TODAY)
    assert any("two" in r.get("note", "") for r in rows) and not (home / "debates" / did / "r2-claude.md").exists()


def test_the_budget_counts_debate_spend(home):
    did = begin(home)["id"]
    debate.run(home, did, execute=True, adapters={s: Scripted(ANSWERS[s]) for s in SEATS},
               today=dt.date.today(), rounds=1)
    newest, tokens, calls = seats._spend(read_run_records(home), dt.datetime.now(dt.timezone.utc))
    assert calls.get("claude") == 1 and tokens.get("claude", 0) > 0


def test_a_pasted_answer_is_not_a_call_this_machine_made(home, tmp_path):
    did = begin(home)["id"]
    put(home, tmp_path, did, 1, "claude", ANSWERS["claude"])
    _newest, tokens, calls = seats._spend(read_run_records(home), dt.datetime.now(dt.timezone.utc))
    assert calls.get("claude", 0) == 0 and tokens.get("claude", 0) == 0


# ---------------------------------------------------------------- cli and docs

def test_cli_start_next_record_score(home, tmp_path, capsys):
    base = ["--home", str(home), "debate"]
    assert main(base + ["start", QUESTION, "--seats", "claude,codex,gemini", "--seed", "cli"]) == 0
    did = re.search(r"D-\d{6}-[0-9a-f]{6}", capsys.readouterr().out).group(0)
    assert main(base + ["next", did]) == 0 and "ROUND 1" in capsys.readouterr().out
    f = tmp_path / "a.txt"
    f.write_text(ANSWERS["claude"], encoding="utf-8")
    assert main(base + ["record", did, "--round", "1", "--seat", "claude", "--file", str(f)]) == 0
    assert main(base + ["score", did]) == 0 and "logged, not used" in capsys.readouterr().out
    assert main(base + ["run", did]) == 0 and "Dry run" in capsys.readouterr().out
    assert main(base + ["next", "D-000000-zzzzzz"]) == 2


def test_the_protocol_doc_matches_the_code():
    doc = (ROOT / "docs" / "DEBATE.md").read_text(encoding="utf-8")
    for word in ("OBJECTION", "DEFENCE", "concede", "rebut", "revise", "revised", "SURVIVED", "FELL", "OPEN", "evidence",
                 "opinion", "logged, not used", "settle", "B*", "unchallenged", "--skip-missing", "--seed", "--json",
                 "--reveal", "--run", "rule 6", "scorecard", str(debate.MAX_OBJECTIONS), str(debate.MAX_CLAIMS)):
        assert word in doc, f"docs/DEBATE.md does not mention {word}"
    for seat in sorted(ask.ADAPTERS):  # the seats the code accepts are the seats the page lists
        assert seat in doc
    assert doc.count("\n") < 150  # one page
    assert doc.strip().startswith("# ")
    for seat_word in debate.PROTOCOL.split():
        assert seat_word.lower() not in SEATS
