"""The seat scorecard: from the same data the verdicts use, what each seat did. Pure counting, no model, no opinion."""
from lifeos import debatestats

LABELS = {"A": "claude", "B": "codex"}


def obj(author, target_seat, label, tid, oid, counts=True):
    return {"author": author, "seat": target_seat, "label": label, "tid": tid, "id": oid, "counts": counts}


def test_each_seat_is_counted_for_its_claims_its_objections_and_its_defences():
    rows = [
        {"target": "A1", "objections": 1, "verdict": "FELL"},
        {"target": "A2", "objections": 1, "verdict": "OPEN"},
        {"target": "A3", "objections": 0, "verdict": "SURVIVED"},
        {"target": "B1", "objections": 1, "verdict": "SURVIVED"},   # survived by a revision
        {"target": "B2", "objections": 0, "verdict": "SURVIVED"},
    ]
    valid = [obj("codex", "claude", "A", "A1", "O1"), obj("codex", "claude", "A", "A2", "O2"),
             obj("codex", "claude", "A", "A3", "-", counts=False), obj("claude", "codex", "B", "B1", "O1")]
    numbered = [v for v in valid if v["counts"]]
    defences = {("A", "O2"): {"response": "rebut"}, ("B", "O1"): {"response": "revise"}}   # A1's objection is unanswered
    card = debatestats.scorecard(LABELS, valid, numbered, defences, rows)
    claude, codex = card["claude"], card["codex"]
    assert (claude["fell"], claude["open"], claude["revised_survivor"], claude["unchallenged"]) == (1, 1, 0, 1)
    assert (codex["fell"], codex["open"], codex["revised_survivor"], codex["unchallenged"]) == (0, 0, 1, 1)
    assert (codex["raised"], codex["counted"], codex["landed"], codex["contested"]) == (3, 2, 1, 1)   # A1 landed, A2 was rebutted
    assert (claude["raised"], claude["counted"], claude["landed"], claude["contested"]) == (1, 1, 0, 1)  # B1 was revised
    assert (claude["unanswered"], claude["conceded"], claude["rebutted"], claude["revised"]) == (1, 0, 1, 0)
    assert (codex["unanswered"], codex["conceded"], codex["rebutted"], codex["revised"]) == (0, 0, 0, 1)


def test_a_concession_lands_the_objection_and_is_counted_for_the_defender():
    valid = [obj("codex", "claude", "A", "A1", "O1")]
    card = debatestats.scorecard(LABELS, valid, valid, {("A", "O1"): {"response": "concede"}},
                                 [{"target": "A1", "objections": 1, "verdict": "FELL"}])
    assert card["codex"]["landed"] == 1 and card["claude"]["conceded"] == 1 and card["claude"]["unanswered"] == 0


def test_a_seat_with_no_activity_is_all_zeros_not_missing():
    card = debatestats.scorecard(LABELS, [], [], {}, [])
    assert set(card) == {"claude", "codex"} and not any(card["claude"].values())


def test_a_seat_that_never_answered_is_not_shown_as_a_row_of_zeros():
    card = debatestats.scorecard(LABELS, [], [], {}, [])
    card["codex"]["answered"] = False
    lines = debatestats.render(card).splitlines()
    assert any(l.startswith("codex") and "no round 1 answer" in l for l in lines)
    assert any(l.startswith("claude") and "no round 1 answer" not in l for l in lines)


def test_render_lists_every_seat_with_plain_headings():
    card = debatestats.scorecard(LABELS, [], [], {}, [{"target": "A1", "objections": 0, "verdict": "SURVIVED"}])
    text = debatestats.render(card)
    assert "claude" in text and "codex" in text and "landed" in text and "conceded" in text
