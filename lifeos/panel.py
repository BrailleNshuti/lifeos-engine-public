"""Blind panel: ask two to four models the same task independently, then report only where they differ.

Every model gets the identical context pack (the task file is cut back to its length at the start, so an earlier
panel member's answer is never in the next one's prompt: rule 7). The report compares the answers claim by claim,
without another model call: what all agree on, what a majority says, conflicts (the same point with different numbers
or opposite wording) and what only one model says. Conflicts and single voices are what a human or the lead model
should check first (rule 6: another AI agreeing is not evidence, so agreement is only the starting point).
"""
import re

from . import ask
from .context import build_pack, pack_hash, task_file
from .store import append_task_note, new_run_id

STOP = frozenset("a an the to of in on at for with and or is are was be been it its this that these those as by from "
                 "we you i should will would can could may might also then so".split())
NEG = frozenset("not no never without avoid cannot".split())
THRESHOLD = 0.6


class PanelError(Exception):
    pass


def _parts(text):
    t = str(text).lower().replace("n't", " not").replace("cannot", "can not")
    words = re.findall(r"[a-z0-9äöüß]+(?:\.[0-9]+)?", t)
    numbers = frozenset(w for w in words if any(c.isdigit() for c in w))
    negated = any(w in NEG for w in words)
    content = frozenset(w for w in words if w not in STOP and w not in NEG and w not in numbers)
    return content, numbers, negated


def same_topic(a, b):
    ca, cb = _parts(a)[0], _parts(b)[0]
    return bool(ca and cb) and len(ca & cb) / len(ca | cb) >= THRESHOLD


def conflicting(a, b):
    if not same_topic(a, b):
        return False
    _, na, ga = _parts(a)
    _, nb, gb = _parts(b)
    return na != nb or ga != gb


def claims(answer):
    """Split an answer into short claims: one per line or sentence, markup and numbering removed."""
    out = []
    for line in str(answer).replace("\r\n", "\n").split("\n"):
        line = re.sub(r"^\s*(?:[-*+•]|\d+[.)])\s*", "", line.strip())
        for part in re.split(r"(?<=[.!?])\s+", line):
            part = re.sub(r"[*_`#]+", "", part).strip()
            if len(re.findall(r"\w+", part)) >= 3:
                out.append(part)
    return out


def compare(answers):
    """answers: {model: text}. Return the report dict."""
    models = list(answers)
    clusters = []
    for model in models:
        for text in claims(answers[model]):
            home = next((c for c in clusters if model not in c["claims"] and same_topic(c["rep"], text)), None)
            if home:
                home["claims"][model] = text
            else:
                clusters.append({"rep": text, "claims": {model: text}})
    rep = {"agreed_by_all": [], "majority": [], "conflicts": [], "single": []}
    for c in clusters:
        said = list(c["claims"].items())
        item = {"text": c["rep"], "models": [m for m, _ in said]}
        if any(conflicting(a, b) for i, (_, a) in enumerate(said) for _, b in said[i + 1:]):
            rep["conflicts"].append({**item, "claims": dict(said)})
        elif len(said) == 1:
            rep["single"].append(item)
        elif len(said) == len(models):
            rep["agreed_by_all"].append(item)
        else:
            rep["majority"].append(item)
    return rep


def render(models, report, pack_sha, failed=None, day=""):
    lines = [f"Models: {', '.join(models)}. Same input for all (pack sha256 {pack_sha[:12]}); no model saw another's answer.",
             f"Agreed by all: {len(report['agreed_by_all'])} · majority: {len(report['majority'])} · "
             f"conflicts: {len(report['conflicts'])} · only one model: {len(report['single'])}"]
    for name, key in (("Conflicts (check first)", "conflicts"), ("Only one model says", "single"), ("Majority", "majority")):
        if report[key]:
            lines += ["", f"{name}:"]
            for c in report[key]:
                if key == "conflicts":
                    lines += [f"- [{m}] {t}" for m, t in c["claims"].items()]
                    lines.append("")
                else:
                    lines.append(f"- [{', '.join(c['models'])}] {c['text']}")
    if report["agreed_by_all"]:
        lines += ["", "Agreed by all (still check the evidence, rule 6):"] + [f"- {c['text']}" for c in report["agreed_by_all"]]
    if failed:
        lines += ["", "Did not answer: " + "; ".join(f"{m} ({why})" for m, why in failed.items())]
    return "\n".join(l for l in lines).strip()


def run_panel(home, models, task_id, budget=6000, adapters=None, today=None, full=False):
    adapters = adapters if adapters is not None else ask.ADAPTERS
    if not 2 <= len(models) <= 4:
        raise PanelError("A panel needs two to four models.")
    if len(set(models)) != len(models):
        raise PanelError("A model cannot sit on the panel twice.")
    unknown = [m for m in models if m not in adapters]
    if unknown:
        raise PanelError(f"Unknown model(s): {', '.join(unknown)}. Choose from: {', '.join(sorted(adapters))}.")
    import datetime as dt
    day = today or dt.date.today()
    path = task_file(home, task_id)
    limit = len(path.read_text(encoding="utf-8"))
    names = None if full else ask.MINIMAL
    pack_sha = pack_hash(build_pack(home, task_id, budget, task_first=True, names=names, task_limit=limit)[0])
    pid, answers, run_ids, failed = new_run_id(day), {}, {}, {}
    for model in models:
        def call(prompt, _m=model):
            text = adapters[_m](prompt)
            answers[_m] = text
            return text
        try:
            ask.run_ask(home, model, task_id, budget, adapters={model: call}, today=day, full=full,
                        run_id=f"{pid}-{model}", task_limit=limit)
            run_ids[model] = f"{pid}-{model}"
        except (ask.AskError, ask.Blocked, ask.ToolMissing) as err:
            failed[model] = str(err).strip().splitlines()[0][:160] if str(err).strip() else type(err).__name__
    if not answers:
        raise PanelError("No model answered: " + "; ".join(f"{m}: {w}" for m, w in failed.items()))
    report = compare({m: answers[m] for m in models if m in answers})
    body = render(list(answers), report, pack_sha, failed, day.isoformat())
    append_task_note(home, path, f"## Panel · {day.isoformat()} · {', '.join(answers)}", body)
    return {"pack_sha256": pack_sha, "run_ids": run_ids, "failed": failed, "report": report, "text": body}
