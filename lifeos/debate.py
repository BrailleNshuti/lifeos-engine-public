"""`lifeos debate`: models answer blind, attack each other's answers, defend, and only ideas that survive on evidence count.

Three rounds. Round 1: every seat gets the identical pack and answers alone. Round 2: each seat sees the OTHER answers
relabeled A, B, C in a seeded order (no model names, no hashes) and raises objections. Round 3: each seat sees only the
objections against its own answer (no author names) and concedes, rebuts or revises. `score` is pure rules, no model:
a point without evidence is an opinion and does not count, and agreement is logged but never decides (rule 6).
The label to seat mapping is seeded, stored in debates/<id>/debate.json and never sent to a seat. See docs/DEBATE.md.
"""
import datetime as dt
import hashlib
import json
import re
import secrets
import sys
import uuid
from pathlib import Path

from . import ask, debatestats, panel, seats, verify
from .home import estimate_tokens
from .policy import TIERS, check_provider_allowed, classify_content
from .store import append_run_record, atomic_write_bytes, read_run_records, run_lock

ROUNDS = 3
MIN_SEATS, MAX_SEATS = 2, 4
MAX_OBJECTIONS = 3  # per attacker, per answer
MAX_CLAIMS = 40  # claims shown per answer
MAX_BYTES = 200_000
ID = re.compile(r"^D-\d{6}-[0-9a-f]{6}$")
NAMES = re.compile(r"\b(claude|codex|gemini|grok|qwen|ollama|chatgpt\w*|gpt[-\w]*|anthropic|openai|deepseek|llama\w*|google|"
                   r"mistral|mixtral|cohere|xai|perplexity|copilot|bard|sonnet|opus|haiku|gemma|kimi|antigravity)\b", re.I)
HEX64 = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")
NO_EVIDENCE = frozenset({"", "none", "n/a", "na", "-", "no", "no evidence", "unknown", "tbd", "?"})
STRONG = re.compile(r"[\w.-]+/[\w.-]+|\b\w+\.(?:py|md|json|jsonl|csv|txt|ya?ml|toml)\b|\w+::\w+|https?://|\w+\(\)|"
                    r"\b(?:git|pytest|python3?|lifeos|grep|rg|curl|npm|pip)\s+\S+")
WEAK = re.compile(r"\d|\w+_\w+")
TARGET = re.compile(r"([A-D])(\d+|\*)?")
OBJ_KEYS = ("target", "claim", "evidence", "kind", "settle")
DEF_KEYS = ("objection", "response", "evidence", "settle", "revised")
SPENT = ("failed", "timeout")  # a call was made

PROTOCOL = """DEBATE PROTOCOL
You are one of several independent experts answering the same question. Answers are anonymous: you never learn who wrote what.
Nothing counts because many agree. Only evidence counts: a file and line, a command and its output, a test, or a source with a date.
A point without evidence is an opinion and is set aside. Never include secrets or private data."""

OBJECTION_FORM = """OBJECTION
target: B2   (the claim you attack; B alone means the whole answer)
claim: what is wrong or missing, in one sentence
evidence: a file and line, command output, test id or source with date. Write none if you have none.
kind: evidence or opinion
settle: the test or check that would settle it (strongly recommended)
END"""

DEFENCE_FORM = """DEFENCE
objection: O1
response: concede or rebut or revise
evidence: what supports your answer. A rebuttal or revision without evidence counts as a concession.
revised: only for revise: the claim as you now state it
settle: the test or check that would settle it (strongly recommended)
END"""


class DebateError(Exception):
    pass


# ---------------------------------------------------------------- small helpers

def _sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else str(data).encode("utf-8")).hexdigest()


def _lf_sha(data):
    """Hash with line endings normalised, so a CRLF checkout of an answer still matches its ledger record."""
    return _sha(data.replace(b"\r\n", b"\n"))


def _scrub(text):
    return HEX64.sub("[hash]", NAMES.sub("[model]", str(text)))


def _scrub_all(value):
    """_scrub applied to every string inside a report, for output that is not the rendered table."""
    if isinstance(value, str):
        return _scrub(value)
    if isinstance(value, list):
        return [_scrub_all(v) for v in value]
    if isinstance(value, dict):
        return {k: _scrub_all(v) for k, v in value.items()}
    return value


def has_evidence(text):
    """Evidence must carry a pointer: a path, file name, test id, URL, call or command (any length), or a number or
    identifier inside a sentence of 4+ words. It checks that a pointer exists, not that it is true or well chosen."""
    t = " ".join(str(text or "").split()).strip(".").lower()
    if t in NO_EVIDENCE:
        return False
    return bool(STRONG.search(t)) or (len(t.split()) >= 4 and bool(WEAK.search(t)))


def make_labels(seat_list, seed):
    """{label: seat} in a seeded order that is stable on every Python version (sorted by a keyed hash)."""
    order = sorted(seat_list, key=lambda s: _sha(f"{seed}:label:{s}"))
    return {chr(65 + i): s for i, s in enumerate(order)}


NUMBERED = re.compile(r"^ {0,3}\d+[.)]\s+")
BULLET = re.compile(r"^ {0,3}[-*+•]\s+")
MARKER = re.compile(r"^\s*(?:\d+[.)]|[-*+•])\s+")
CLIP = 160


def clip(text, limit=CLIP):
    text = str(text)
    return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."


def _items(answer):
    """The points the seat wrote: a numbered item (or a bullet, or a paragraph) with its sub-lines and evidence attached."""
    lines = str(answer).replace("\r\n", "\n").split("\n")
    start = NUMBERED if any(NUMBERED.match(l) for l in lines) else BULLET
    items, blank = [], True
    for raw in lines:
        if not raw.strip():
            blank = True
            continue
        indented = raw.startswith((" ", "\t")) and not start.match(raw)
        if start.match(raw) or (blank and not indented) or not items:
            items.append([raw])
        else:
            items[-1].append(raw)
        blank = False
    return items, any(start.match(l) for l in lines)


def claims_of(answer):
    """One claim per point of the answer, in order. Prose with no list and no paragraphs is split into sentences instead."""
    items, marked = _items(answer)
    texts = []
    for item in items:
        text = " ".join(MARKER.sub("", l.strip()) for l in item)
        text = re.sub(r"[*`]+|^#+\s*", "", text)
        texts.append(" ".join(text.split()))
    if len(items) == 1 and not marked:
        texts = panel.claims(answer)
    return [_scrub(t) for t in texts if len(re.findall(r"\w+", t)) >= 3][:MAX_CLAIMS]


def agreement(answers):
    """Claims two or more seats made. Logged for the owner, never used to decide anything."""
    if len(answers) < 2:
        return 0
    rep = panel.compare(answers)
    return len(rep["agreed_by_all"]) + len(rep["majority"])


def _folder(home, did):
    if not ID.match(str(did)):
        raise DebateError(f"'{did}' is not a debate id (expected something like D-261120-a1b2c3).")
    return Path(home) / "debates" / did


def _canon(meta):
    return _sha(json.dumps(meta, sort_keys=True, separators=(",", ":")))


def load(home, did):
    """Read debate.json and prove it is the one `start` made: the ledger chain is intact, the file's hash sits in it, and
    the stored round 1 pack still hashes to pack_sha256. A swapped seed or label mapping is caught here, before any
    command (next, record, run, score) trusts it."""
    path = _folder(home, did) / "debate.json"
    if not path.exists():
        raise DebateError(f"No debate {did} in {path.parent.parent}.")
    if not verify.verify_chain(home)["ok"]:
        raise DebateError("The ledger chain is broken, so the debate cannot be trusted. Run `lifeos verify`.")
    meta = json.loads(path.read_text(encoding="utf-8"))
    began = [r for r in read_run_records(home) if r.get("run_id") == f"{did}-start"]
    if not began or began[0].get("meta_sha256") != _canon(meta):
        raise DebateError(f"debate.json of {did} changed after it was created (or its ledger record is missing).")
    pack = path.parent / "prompts" / "r1.txt"
    if not pack.exists() or _lf_sha(pack.read_bytes()) != meta.get("pack_sha256"):
        raise DebateError(f"prompts/r1.txt of {did} changed after it was created.")
    return meta


def _records(home, did):
    return [r for r in read_run_records(home) if r.get("command") == "debate" and r.get("debate_id") == did]


def _ok(recs, rnd):
    return {r["model"].split(":")[0]: r for r in recs if r.get("round") == rnd and r.get("status") == "ok"}


def _write(path, text):
    atomic_write_bytes(path, text.encode("utf-8"))


# ---------------------------------------------------------------- prompts

def r1_prompt(question):
    return (f"{PROTOCOL}\n\nROUND 1 of {ROUNDS}. Answer on your own.\nWrite short numbered claims, one claim per line, "
            "each followed by its evidence. End with one line: what would prove you wrong.\n\n"
            f"QUESTION:\n{question}\n")


def r2_prompt(meta, viewer, answers):
    """answers: {seat: text} of the OTHER seats. Seat names are replaced by labels, in an order seeded per viewer."""
    lab = {s: l for l, s in meta["labels"].items()}
    order = sorted(answers, key=lambda s: _sha(f"{meta['seed']}:r2:{viewer}:{lab[s]}"))
    blocks = []
    for seat in order:
        lines = [f"{lab[seat]}{i}. {c}" for i, c in enumerate(claims_of(answers[seat]), 1)]
        blocks.append(f"=== ANSWER {lab[seat]} ===\n" + "\n".join(lines))
    return (f"{PROTOCOL}\n\nROUND 2 of {ROUNDS}. Attack the answers below. Each answer is anonymous and its claims are "
            f"numbered. Give at most {MAX_OBJECTIONS} objections per answer, each in exactly this form:\n{OBJECTION_FORM}\n"
            "An objection with no evidence is an opinion and does not count.\n\n"
            f"QUESTION:\n{meta['question']}\n\n" + "\n\n".join(blocks) + "\n")


def r3_prompt(meta, own_claims, objections, set_aside):
    """objections: counted ones against this seat's answer, without authors."""
    lines = []
    for o in objections:
        where = f"your claim {o['idx']}: \"{clip(own_claims[o['idx'] - 1], 300)}\"" if o["idx"] else "your answer as a whole"
        lines += [f"[{o['id']}] against {where}", f"claim: {_scrub(o['says'])}",
                  f"evidence: {_scrub(o['evidence'])}"] + ([f"settle: {_scrub(o['settle'])}"] if o["settle"] else []) + [""]
    aside = f"{set_aside} objection(s) without evidence were set aside as opinion.\n" if set_aside else ""
    return (f"{PROTOCOL}\n\nROUND 3 of {ROUNDS}. Others raised the objections below against your answer. Reply to each "
            f"one, in exactly this form:\n{DEFENCE_FORM}\n{aside}\nQUESTION:\n{meta['question']}\n\n"
            "OBJECTIONS:\n" + "\n".join(lines))


# ---------------------------------------------------------------- parsing

def _blocks(text, head, keys):
    out, cur, last = [], None, None
    for raw in str(text).replace("\r\n", "\n").split("\n"):
        line = re.sub(r"^[\s>*#\-•]+", "", raw).replace("**", "").replace("`", "").strip()
        if re.fullmatch(head, line, re.I):
            cur, last = {}, None
            out.append(cur)
        elif cur is None:
            continue
        elif re.fullmatch(r"END\W*", line, re.I):
            cur = None
        elif (m := re.match(r"([A-Za-z]+)\s*:\s*(.*)$", line)) and m.group(1).lower() in keys:
            last = m.group(1).lower()
            cur[last] = m.group(2).strip()
        elif line and last:
            cur[last] += " " + line
    return out


def parse_objections(text):
    """Every block is returned. It counts only with a target, a claim, exactly `kind: evidence` and checkable evidence.
    The cap of MAX_OBJECTIONS per answer is applied later, to objections that point at something real."""
    out = []
    for b in _blocks(text, r"OBJECTION\s*\d*\s*:?", OBJ_KEYS):
        m = TARGET.fullmatch(b.get("target", "").upper().replace(" ", ""))
        label = m.group(1) if m else None
        idx = int(m.group(2)) if m and m.group(2) and m.group(2) != "*" else None
        evidence = b.get("evidence", "")
        counts = (bool(label) and bool(b.get("claim", "").strip()) and b.get("kind", "").strip().strip(".*").lower() == "evidence"
                  and has_evidence(evidence))
        out.append({"target": b.get("target", "").strip().upper(), "label": label, "idx": idx, "claim": b.get("claim", ""),
                    "evidence": evidence, "kind": "evidence" if counts else "opinion", "settle": b.get("settle", ""),
                    "counts": counts})
    return out


def parse_defences(text):
    out, seen = [], set()
    for b in _blocks(text, r"DEFEN[CS]E\s*\d*\s*:?", DEF_KEYS):
        oid = re.search(r"O\d+", b.get("objection", "").upper())
        word = (b.get("response", "").lower().split() or [""])[0].strip(".,;:")
        if not oid or oid.group(0) in seen or word not in ("concede", "rebut", "revise"):
            continue
        seen.add(oid.group(0))
        if word != "concede" and not has_evidence(b.get("evidence", "")):
            word = "concede"  # a rebuttal or revision without evidence is a concession
        if word == "revise" and not b.get("revised", "").strip():
            word = "concede"  # a revision must say what the claim now is
        out.append({"objection": oid.group(0), "response": word, "evidence": b.get("evidence", ""),
                    "settle": b.get("settle", ""), "revised": b.get("revised", "")})
    return out


# ---------------------------------------------------------------- start / record

def start(home, question, seat_list, seed=None, today=None):
    seat_list = [s.strip() for s in seat_list]
    if not MIN_SEATS <= len(seat_list) <= MAX_SEATS or len(set(seat_list)) != len(seat_list):
        raise DebateError(f"A debate needs {MIN_SEATS} to {MAX_SEATS} different seats.")
    unknown = [s for s in seat_list if s not in ask.ADAPTERS]
    if unknown:
        raise DebateError(f"Unknown seat(s): {', '.join(unknown)}. Choose from: {', '.join(sorted(ask.ADAPTERS))}.")
    q = str(question or "").strip()
    if not q:
        raise DebateError("The debate needs a question.")
    if NAMES.search(q):
        raise DebateError("The question names a seat or a provider; a blind debate may not. Rephrase it.")
    ask.check_text(q, "the question", "Nothing was created.")
    if classify_content(q, "debates/question") == "SECRET":
        raise DebateError("SECRET data cannot be sent to any model.")
    if not (Path(home) / "logs").is_dir():
        raise DebateError("This home has no logs/ folder, so the ledger record cannot be written.")
    day = today or dt.date.today()
    did = f"D-{day:%y%m%d}-{uuid.uuid4().hex[:6]}"
    seed = seed or secrets.token_hex(6)
    pack = r1_prompt(q)
    meta = {"id": did, "version": 1, "created": day.isoformat(), "question": q, "seats": seat_list, "seed": seed,
            "labels": make_labels(seat_list, seed), "pack_sha256": _sha(pack)}
    folder = _folder(home, did)
    (folder / "prompts").mkdir(parents=True)
    _write(folder / "prompts" / "r1.txt", pack)
    _write(folder / "debate.json", json.dumps(meta, indent=2, sort_keys=True) + "\n")
    append_run_record(home, {"run_id": f"{did}-start", "command": "debate", "date": day.isoformat(), "model": "debate",
                             "status": "ok", "debate_id": did, "round": 0, "source": "start", "meta_sha256": _canon(meta)})
    return meta


def _record(home, meta, rnd, seat, text, day, source, prompt=None, status="ok", error=None, phase=None):
    """One ledger record per answer or failure. The answer file is written first and never overwritten."""
    did = meta["id"]
    base = f"{did}-r{rnd}-{seat}"
    rec = {"run_id": base if status == "ok" else f"{base}-x{uuid.uuid4().hex[:6]}", "command": "debate",
           "date": day.isoformat(), "model": ask.label(seat), "status": status, "debate_id": did, "round": rnd,
           "source": source}
    if prompt is not None:
        rec["prompt_sha256"] = _sha(prompt)
        if status == "ok" or status in SPENT:
            rec["tokens"] = estimate_tokens(prompt)
    if error:
        rec["error"] = ask.redact_error(error)
    if phase:
        rec["phase"] = phase
    if status != "ok":
        append_run_record(home, rec)
        return rec
    data = text.replace("\r\n", "\n").encode("utf-8")
    target = _folder(home, did) / f"r{rnd}-{seat}.md"
    rec["answer_sha256"] = _sha(data)
    with run_lock(home, base):
        if any(r.get("run_id") == base for r in _records(home, did)):
            raise DebateError(f"Round {rnd} for {seat} is already recorded.")
        if target.exists() and _lf_sha(target.read_bytes()) != rec["answer_sha256"]:
            raise DebateError(f"Round {rnd} for {seat} is already recorded (a different answer is stored).")
        if not target.exists():
            _write(target, data.decode("utf-8"))
        append_run_record(home, rec)
    return rec


def record(home, did, rnd, seat, file, today=None):
    if not (Path(home) / "logs").is_dir():
        raise DebateError("This home has no logs/ folder, so the ledger record cannot be written.")
    meta = load(home, did)
    if seat not in meta["seats"] or not 1 <= rnd <= ROUNDS:
        raise DebateError(f"Seat must be one of {', '.join(meta['seats'])} and round 1 to {ROUNDS}.")
    raw = Path(file).read_bytes()
    if len(raw) > MAX_BYTES:
        raise DebateError(f"The answer is over {MAX_BYTES} bytes.")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise DebateError("The answer is not valid UTF-8 text.") from None
    if not text.strip():
        raise DebateError("The answer file is empty.")
    ask.check_text(text, "the answer", "Nothing was stored.")
    rec = _record(home, meta, rnd, seat, text, today or dt.date.today(), "manual")
    return {"sha256": rec["answer_sha256"], "path": _folder(home, did) / f"r{rnd}-{seat}.md", "run_id": rec["run_id"]}


def _answers(home, meta, rnd, recs):
    """{seat: text} of the recorded answers, each checked against the hash the ledger holds."""
    out = {}
    for seat, rec in _ok(recs, rnd).items():
        path = _folder(home, meta["id"]) / f"r{rnd}-{seat}.md"
        if not path.exists():
            raise DebateError(f"{path.name} is missing although the ledger recorded it.")
        if _lf_sha(path.read_bytes()) != rec.get("answer_sha256"):
            raise DebateError(f"{path.name} changed after it was recorded; the debate cannot be scored.")
        out[seat] = path.read_text(encoding="utf-8")
    return out


# ---------------------------------------------------------------- objections and scoring

def _valid_objections(meta, a1, a2):
    """Objections from round 2 that point at a real claim of another seat, at most MAX_OBJECTIONS per author and answer
    (invalid ones do not use up the cap). Returns (valid, ignored_count); everything not valid is counted as ignored."""
    lab = {s: l for l, s in meta["labels"].items()}
    valid, ignored, used = [], 0, {}
    for author, text in a2.items():
        for o in parse_objections(text):
            seat = meta["labels"].get(o["label"])
            n = len(claims_of(a1[seat])) if seat in a1 else 0
            if not seat or seat == author or seat not in a1 or (o["idx"] is not None and not 1 <= o["idx"] <= n):
                ignored += 1
                continue
            used[(author, seat)] = used.get((author, seat), 0) + 1
            if used[(author, seat)] > MAX_OBJECTIONS:
                ignored += 1
                continue
            valid.append({**o, "author": author, "seat": seat, "tid": f"{lab[seat]}{o['idx'] or '*'}"})
    return valid, ignored


def _numbered(meta, valid):
    """Give each counted objection a per-answer id (O1, O2, ...) in a seeded order that hides the author."""
    out = []
    for label in meta["labels"]:
        mine = [o for o in valid if o["counts"] and o["label"] == label]
        mine.sort(key=lambda o: _sha(f"{meta['seed']}:o:{label}:{o['author']}:{o['tid']}:{o['claim']}"))
        out += [{**o, "id": f"O{i}"} for i, o in enumerate(mine, 1)]
    return out


def _round2(home, meta, recs):
    a1, a2 = _answers(home, meta, 1, recs), _answers(home, meta, 2, recs)
    valid, ignored = _valid_objections(meta, a1, a2)
    return a1, valid, ignored


def objections_against(home, did, seat):
    """The counted objections against this seat's answer, numbered and without authors (what round 3 shows)."""
    meta, recs = load(home, did), _records(home, did)
    _a1, valid, _ignored = _round2(home, meta, recs)
    return [_public(o) for o in _numbered(meta, valid) if o["seat"] == seat]


def _public(o):
    """What a defender may see of an objection: no author, no seat."""
    return {"id": o["id"], "target": o["tid"], "idx": o["idx"], "says": o["claim"], "evidence": o["evidence"],
            "settle": o["settle"]}


def _verdict(items, defences):
    """FELL if any counted objection was conceded or went unanswered; else OPEN if any was rebutted with evidence
    (evidence on both sides, which no rule can settle); else SURVIVED (nothing counted, or every one revised)."""
    fell, opened, why, settle, pairs, revised = [], False, [], [], [], []
    for o in items:
        d = defences.get((o["label"], o["id"]))
        if d is None:
            fell.append(f"unanswered {o['id']}")
        elif d["response"] == "concede":
            fell.append(f"conceded {o['id']}")
        elif d["response"] == "revise":
            revised.append(f"{o['id']} revised to \"{d['revised']}\"")
        elif d["response"] == "rebut":
            opened = True
            settle += [o["settle"], d["settle"]]
            pairs.append(f"\"{o['evidence']}\" against \"{d['evidence']}\"")
            why.append(f"{o['id']} has evidence on both sides")
    settle = [s for s in dict.fromkeys(settle) if s]
    if fell:
        return "FELL", ", ".join(fell), settle
    if opened:
        return "OPEN", "; ".join(why), settle or ["no settling test was proposed; check both pieces of evidence: " + "; ".join(pairs)]
    return "SURVIVED", ("; ".join(revised) + ": read the revision, it can change the claim") if items else "unchallenged (not verified)", settle


def _defences(meta, a3):
    out = {}
    for seat, text in a3.items():
        label = next(l for l, s in meta["labels"].items() if s == seat)
        out.update({(label, d["objection"]): d for d in parse_defences(text)})
    return out


def _rows(meta, a1, groups, defences):
    """One row per claim: challenged ones get a verdict from the rules, the rest are SURVIVED as unchallenged. An answer
    with a counted whole-answer objection gets one row for it (`B*`) and its claims are covered by that row."""
    rows = []
    for label, seat in meta["labels"].items():
        if seat not in a1:
            continue
        claims = claims_of(a1[seat])
        wanted = [(f"{label}*", "(the whole answer)")] if f"{label}*" in groups else []
        wanted += [(f"{label}{i}", c) for i, c in enumerate(claims, 1) if f"{label}*" not in groups or f"{label}{i}" in groups]
        for tid, text in wanted:
            items = groups.get(tid, [])
            v, why, settle = _verdict(items, defences)
            rows.append({"target": tid, "text": text, "objections": len(items), "verdict": v, "why": why, "settle": settle})
    return rows


def score(home, did):
    meta, recs = load(home, did), _records(home, did)
    a1, valid, ignored = _round2(home, meta, recs)
    numbered, groups = _numbered(meta, valid), {}
    for o in numbered:
        groups.setdefault(o["tid"], []).append(o)
    defences = _defences(meta, _answers(home, meta, 3, recs))
    rows = _rows(meta, a1, groups, defences)
    total = sum(len(claims_of(t)) for t in a1.values())
    return {"debate": did, "question": meta["question"], "labels": meta["labels"], "claims_total": total,
            "answered": {r: len(_ok(recs, r)) for r in range(1, ROUNDS + 1)}, "claims": rows,
            "challenged": [r for r in rows if r["objections"]], "unchallenged": sum(not r["objections"] for r in rows),
            "opinion_set_aside": sum(not o["counts"] for o in valid), "ignored": ignored, "agreement_logged": agreement(a1),
            "seats": {seat: {**stats, "answered": seat in a1}
                      for seat, stats in debatestats.scorecard(meta["labels"], valid, numbered, defences, rows).items()}}


def render_score(rep, reveal=False):
    clean = (lambda t: str(t)) if reveal else _scrub
    ans = rep["answered"]
    lines = [f"Debate {rep['debate']} · answers recorded: " + " · ".join(f"round {r}: {n}" for r, n in ans.items()),
             f"Question: {rep['question']}", ""]
    lines.append("claim  verdict   objections  what")
    for c in rep["claims"]:
        lines.append(f"{c['target']:6} {c['verdict']:9} {c['objections']:<11} \"{clean(clip(c['text']))}\" · {clean(c['why'])}".rstrip(" ·"))
        lines += [f"       settle with: {clean(s)}" for s in c["settle"]] if c["verdict"] == "OPEN" else []
    lines += ["", f"Unchallenged claims: {rep['unchallenged']} of {rep['claims_total']} (SURVIVED means nobody showed otherwise, "
                  f"not that it is true) · opinions set aside (no evidence): {rep['opinion_set_aside']} · "
                  f"objections ignored (bad target or over the cap of {MAX_OBJECTIONS}): {rep['ignored']}",
              f"Agreement (logged, not used): {rep['agreement_logged']} claim(s) made by two or more seats."]
    if reveal:
        lines += ["Labels: " + ", ".join(f"{l}={s}" for l, s in rep["labels"].items()), "", debatestats.render(rep["seats"])]
    return "\n".join(lines)


# ---------------------------------------------------------------- rounds

def _participants(home, meta, rnd, recs):
    if rnd == 1:
        return list(meta["seats"])
    if rnd == 2:
        return [s for s in meta["seats"] if s in _ok(recs, 1)]
    _a1, valid, _ig = _round2(home, meta, recs)
    hit = {o["seat"] for o in valid if o["counts"]}
    return [s for s in meta["seats"] if s in hit]


def _terminal(recs, rnd):
    return {r["model"].split(":")[0] for r in recs if r.get("round") == rnd}


def _current(home, meta, recs):
    for rnd in range(1, ROUNDS + 1):
        if rnd > 1 and len(_ok(recs, 1)) < MIN_SEATS:
            return rnd
        if set(_participants(home, meta, rnd, recs)) - _terminal(recs, rnd):
            return rnd
    return ROUNDS


def next_round(home, did, rnd=None, skip_missing=False):
    """Prompts for the seats that still owe an answer in this round (the first unfinished round by default)."""
    meta, recs = load(home, did), _records(home, did)
    rnd = rnd or _current(home, meta, recs)
    if not 1 <= rnd <= ROUNDS:
        raise DebateError(f"Round must be 1 to {ROUNDS}.")
    out = {"round": rnd, "prompts": {}, "paths": {}, "waiting": []}
    if rnd > 1:
        waiting = sorted(set(_participants(home, meta, rnd - 1, recs)) - _terminal(recs, rnd - 1))
        if waiting and not skip_missing:
            out["waiting"] = waiting
            return out
        if len(_ok(recs, 1)) < MIN_SEATS:
            raise DebateError(f"A debate needs two answers in round 1; only {len(_ok(recs, 1))} recorded.")
    owed = [s for s in _participants(home, meta, rnd, recs) if s not in _ok(recs, rnd)]
    prompts = {1: lambda s: r1_prompt(meta["question"]), 2: lambda s: r2_prompt(meta, s, _others(home, meta, recs, s)),
               3: lambda s: _r3(home, meta, recs, s)}[rnd]
    folder = _folder(home, did) / "prompts"
    for seat in owed:
        out["prompts"][seat] = prompts(seat)
        out["paths"][seat] = folder / ("r1.txt" if rnd == 1 else f"r{rnd}-{seat}.txt")
        if rnd > 1:
            ask.check_text(out["prompts"][seat], "the debate prompt", "No prompt file was written.")
            _write(out["paths"][seat], out["prompts"][seat])
    return out


def _others(home, meta, recs, viewer):
    return {s: t for s, t in _answers(home, meta, 1, recs).items() if s != viewer}


def _r3(home, meta, recs, seat):
    a1, valid, _ig = _round2(home, meta, recs)
    mine = [_public(o) for o in _numbered(meta, valid) if o["seat"] == seat]
    aside = sum(1 for o in valid if o["seat"] == seat and not o["counts"])
    return r3_prompt(meta, claims_of(a1[seat]), mine, aside)


# ---------------------------------------------------------------- run

def _attempt(home, meta, rnd, seat, prompt, adapters, tier, day):
    """Send one prompt to one seat. Returns (status, note). A seat that is down is skipped, never replaced."""
    resting = seats.pressure(read_run_records(home), dt.datetime.now(dt.timezone.utc))
    tier = max(tier, classify_content(prompt, "debates/prompt"), key=TIERS.index)  # the assembled prompt counts too
    skip = None
    if seat not in adapters:
        skip = ("tool_missing", None, "not available on this computer")
    elif seat in resting:
        skip = ("blocked", "resting", f"resting: {resting[seat]}")
    elif seat in ask.PROVIDERS and not check_provider_allowed(tier, seat)[0]:
        skip = ("blocked", "provider_policy", f"the question is {tier}; {seat} may not see it")
    if skip:
        _record(home, meta, rnd, seat, None, day, "run", status=skip[0], error=skip[2], phase=skip[1])
        return "skipped", skip[2]
    try:
        ask.check_text(prompt, "the debate prompt", "Nothing was sent.")
        text = adapters[seat](prompt)
    except ask.Blocked as err:
        return _fail(home, meta, rnd, seat, day, prompt, "blocked", err, "outbound_context")
    except ask.ToolMissing as err:
        return _fail(home, meta, rnd, seat, day, prompt, "tool_missing", err, None)
    except ask.AskError as err:
        return _fail(home, meta, rnd, seat, day, prompt, "timeout" if seats.failure_kind(err) == "timeout" else "failed", err, None)
    except Exception as err:  # a crashing adapter must not take the debate down
        return _fail(home, meta, rnd, seat, day, prompt, "failed", f"{seat} failed: {err}", None)
    try:
        ask.check_text(text, "the answer", "Nothing was stored.")
        if not str(text).strip():
            raise ask.AskError("the seat returned an empty answer")
    except ask.Blocked as err:
        return _fail(home, meta, rnd, seat, day, prompt, "blocked", err, "inbound_answer")
    except ask.AskError as err:
        return _fail(home, meta, rnd, seat, day, prompt, "failed", err, None)
    _record(home, meta, rnd, seat, str(text), day, "run", prompt=prompt)
    return "ok", ""


def _fail(home, meta, rnd, seat, day, prompt, status, err, phase):
    _record(home, meta, rnd, seat, None, day, "run", prompt=prompt, status=status, error=err, phase=phase)
    return ("blocked" if status == "blocked" else "failed"), ask.redact_error(err)[:160]


def run(home, did, execute=False, adapters=None, today=None, rounds=ROUNDS):
    """Dry run unless execute: list who would be asked. With execute, run the rounds in order and skip seats that are down."""
    adapters = ask.ADAPTERS if adapters is None else adapters
    meta, day = load(home, did), today or dt.date.today()
    tier = classify_content(meta["question"], "debates/question")
    resting = seats.pressure(read_run_records(home), dt.datetime.now(dt.timezone.utc))
    rows = []
    first = _current(home, meta, _records(home, did))
    for rnd in range(first if not execute else 1, (first if not execute else rounds) + 1):
        try:
            plan = next_round(home, did, rnd=rnd, skip_missing=True)
        except DebateError as err:
            rows.append({"round": rnd, "seat": "-", "status": "stopped", "note": str(err)})
            break
        for seat, prompt in plan["prompts"].items():
            if not execute:
                gone = "not available on this computer" if seat not in adapters else (f"resting: {resting[seat]}" if seat in resting else "")
                rows.append({"round": rnd, "seat": seat, "status": "skipped" if gone else "planned",
                             "note": gone or f"would send about {estimate_tokens(prompt)} tokens"})
                continue
            status, note = _attempt(home, meta, rnd, seat, prompt, adapters, tier, day)
            rows.append({"round": rnd, "seat": seat, "status": status, "note": note})
    return rows


def render_run(rows, execute):
    lines = [f"round {r['round']}  {r['seat']:7} {r['status']:8} {r['note']}".rstrip() for r in rows]
    if not execute:
        lines.append("Dry run: nothing was sent. Later rounds depend on the answers. Add --run to send.")
    return "\n".join(lines)


# ---------------------------------------------------------------- command line

def register(sub, find_home):
    p = sub.add_parser("debate", help="blind answers, objections and defences; rules score the evidence, never the votes")
    act = p.add_subparsers(dest="debate_action", required=True)
    st = act.add_parser("start", help="create a debate with a question and the seats that will answer")
    st.add_argument("question")
    st.add_argument("--seats", required=True, help="two to four seats, e.g. claude,codex,gemini")
    st.add_argument("--seed", help="fix the label order (default: random, stored)")
    for name, text in (("next", "write the prompt files for the next round (round 1 prints the pack)"),
                       ("run", "ask the seats (dry run unless --run)"),
                       ("score", "score the debate by rules, no model")):
        sp = act.add_parser(name, help=text)
        sp.add_argument("id")
        if name == "next":
            sp.add_argument("--round", type=int)
            sp.add_argument("--skip-missing", action="store_true", help="go on without seats that have not answered")
        if name == "run":
            sp.add_argument("--run", action="store_true")
        if name == "score":
            sp.add_argument("--reveal", action="store_true", help="show which seat wore which label")
            sp.add_argument("--json", action="store_true")
    rc = act.add_parser("record", help="store one answer (round, seat, file) with its hash and a ledger record")
    rc.add_argument("id")
    rc.add_argument("--round", type=int, required=True)
    rc.add_argument("--seat", required=True)
    rc.add_argument("--file", required=True)
    p.set_defaults(func=lambda args: command(args, find_home(args.home)))


def command(args, home):
    try:
        return _dispatch(args, home)
    except DebateError as err:
        print(f"lifeos: {err}", file=sys.stderr)
        return 2
    except (ask.Blocked, ask.ToolMissing, ask.AskError) as err:
        print(f"lifeos: {err}", file=sys.stderr)
        return 3


def _dispatch(args, home):
    act = args.debate_action
    if act == "start":
        meta = start(home, args.question, args.seats.split(","), seed=args.seed)
        print(f"Debate {meta['id']} created in debates/{meta['id']}/ · seats: {', '.join(meta['seats'])} · "
              f"pack sha256 {meta['pack_sha256'][:12]}\nNext: lifeos debate next {meta['id']}")
    elif act == "next":
        out = next_round(home, args.id, rnd=args.round, skip_missing=args.skip_missing)
        print(f"Round {out['round']} of {ROUNDS}" + (f" · waiting for: {', '.join(out['waiting'])}" if out["waiting"] else ""))
        if out["round"] == 1 and out["prompts"]:
            print("Every seat gets exactly this pack:\n\n" + next(iter(out["prompts"].values())))
        else:
            print("\n".join(f"{seat}: {path}" for seat, path in out["paths"].items()))
    elif act == "record":
        out = record(home, args.id, args.round, args.seat, args.file)
        print(f"Recorded round {args.round} for {args.seat} · sha256 {out['sha256'][:12]} · ledger {out['run_id']}")
    elif act == "run":
        print(render_run(run(home, args.id, execute=args.run), args.run))
    else:
        rep = score(home, args.id)
        shown = rep if args.reveal else _scrub_all({k: v for k, v in rep.items() if k not in ("labels", "seats")})
        print(json.dumps(shown, indent=2) if args.json else render_score(rep, reveal=args.reveal))
    return 0
