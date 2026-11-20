"""What each seat did in a debate, counted from the same data the verdicts use. No model, no judgement.

A seat has claims (how its own claims ended up), objections (what it raised and what became of them) and defences (what it did
when objected to). It names seats, so it is shown only with `lifeos debate score --reveal`. It is evidence for choosing seats
(rule 2), not a ranking: one debate is a small sample, and a seat that is right can still have conceded.
"""
ROWS = ("fell", "open", "revised_survivor", "unchallenged", "raised", "counted", "landed", "contested",
        "conceded", "unanswered", "rebutted", "revised")


def scorecard(labels, valid, numbered, defences, rows):
    """labels {A: seat}; valid = every objection that pointed at a real claim; numbered = the counted ones, with ids;
    defences {(label, id): {response}}; rows = the per-claim rows of the score."""
    card = {seat: dict.fromkeys(ROWS, 0) for seat in labels.values()}
    for row in rows:
        mine = card[labels[row["target"][0]]]
        if not row["objections"]:
            mine["unchallenged"] += 1
        elif row["verdict"] == "FELL":
            mine["fell"] += 1
        elif row["verdict"] == "OPEN":
            mine["open"] += 1
        else:
            mine["revised_survivor"] += 1
    for o in valid:
        card[o["author"]]["raised"] += 1
        card[o["author"]]["counted"] += bool(o["counts"])
    for o in numbered:
        answer = defences.get((o["label"], o["id"]))
        said = answer["response"] if answer else None
        card[o["author"]]["contested" if said in ("rebut", "revise") else "landed"] += 1
        card[o["seat"]]["unanswered" if said is None else {"concede": "conceded", "rebut": "rebutted", "revise": "revised"}[said]] += 1
    return card


def render(card):
    head = f"{'seat':8} {'fell':>4} {'open':>4} {'held*':>5} {'unch.':>5} | {'raised':>6} {'counted':>7} {'landed':>6} {'contested':>9} | " \
           f"{'conceded':>8} {'unanswered':>10} {'rebutted':>8} {'revised':>7}"
    lines = [head]
    for seat, c in card.items():
        if c.get("answered") is False:
            lines.append(f"{seat:8} (no round 1 answer was recorded: it did not take part, which is not the same as doing nothing)")
            continue
        lines.append(f"{seat:8} {c['fell']:>4} {c['open']:>4} {c['revised_survivor']:>5} {c['unchallenged']:>5} | {c['raised']:>6} "
                     f"{c['counted']:>7} {c['landed']:>6} {c['contested']:>9} | {c['conceded']:>8} {c['unanswered']:>10} "
                     f"{c['rebutted']:>8} {c['revised']:>7}")
    lines.append("* held after a revision. One debate is a small sample; this is evidence, not a ranking.")
    return "\n".join(lines)
