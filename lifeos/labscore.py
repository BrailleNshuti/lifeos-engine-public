"""Offline deterministic scoring methods for Prompt Lab (layer 0, stdlib only)."""
import hashlib
import json
import re


class ScoreRefused(ValueError):
    """Raised when a results file or check specification violates a Prompt Lab scoring rule."""


def _hash_text(text):
    cleaned = [line.rstrip(" \t\r") for line in text.splitlines()]
    while cleaned and not cleaned[0]:
        cleaned.pop(0)
    while cleaned and not cleaned[-1]:
        cleaned.pop()
    return hashlib.sha256("\n".join(cleaned).encode("utf-8")).hexdigest()[:12]

RESULTS_HEAD_RE = re.compile(r"^#\s*Lab results\s*·\s*(.+?)\s*·\s*v(\d+)\s*$")
CITATION_SENTENCE_RE = re.compile(r"^(.+?)\[([A-Za-z0-9_\-]+),\s*(\d{4}-\d{2}-\d{2})\][.!?]?$")
MANUAL_LINE_RE = re.compile(r"^(T[1-5]):\s*(pass|fail)\b(.*)$", re.I)


def _json_strict_equal(a, b):
    """Strict recursive JSON comparison: True is not 1, 1 is not 1.0, key order ignored."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return set(a.keys()) == set(b.keys()) and all(_json_strict_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_json_strict_equal(x, y) for x, y in zip(a, b))
    return a == b


def _check_sources(arg, trimmed):
    """Verify every sentence closes with a declared [<id>, <date>] and sentence count <= max."""
    sources = {}
    max_sentences = None
    for token in arg.split():
        if "=" not in token:
            raise ScoreRefused(f"bad sources token {token!r}")
        k, v = token.split("=", 1)
        if k == "max":
            max_sentences = int(v)
        else:
            sources[k] = v
    if not sources or max_sentences is None or max_sentences < 1:
        raise ScoreRefused(f"sources check requires '<id>=<date> ... max=<n>', got {arg!r}")

    # Split at sentence boundaries immediately following a citation bracket `].` / `]!` / `]?` or newline
    parts = [p.strip() for p in re.split(r"(?<=\][.!?])\s+|\n+", trimmed) if p.strip()]
    if not parts or len(parts) > max_sentences:
        return False
    for part in parts:
        m = CITATION_SENTENCE_RE.match(part)
        if not m:
            return False
        body, src_id, src_date = m.group(1).strip(), m.group(2), m.group(3)
        if not body or sources.get(src_id) != src_date:
            return False
        # Reject if there is an earlier sentence boundary inside body that had no citation
        if re.search(r"[.!?]\s+[A-Z]", body):
            return False
    return True


def check_one(method, arg, output, manual_verdict=None):
    """Evaluate one `check: <method> <arg>` line against `output`. Empty output always scores False."""
    trimmed = output.strip()
    if not trimmed:
        return False
    if method == "exact":
        return trimmed == arg
    if method == "exact/i":
        return trimmed.casefold() == arg.casefold()
    if method == "has":
        return arg in trimmed
    if method == "has/i":
        return arg.casefold() in trimmed.casefold()
    if method == "lacks":
        return arg not in trimmed
    if method == "lacks/i":
        return arg.casefold() not in trimmed.casefold()
    if method == "json":
        try:
            expected = json.loads(arg)
        except json.JSONDecodeError as err:
            raise ScoreRefused(f"invalid JSON in card check: {arg!r}") from err
        if not isinstance(expected, dict):
            raise ScoreRefused("json check expects a JSON object")
        try:
            actual = json.loads(trimmed)
        except json.JSONDecodeError:
            return False
        return _json_strict_equal(expected, actual)
    if method == "sources":
        return _check_sources(arg, trimmed)
    if method == "manual":
        if manual_verdict not in ("pass", "fail"):
            raise ScoreRefused("missing manual verdict in ## manual")
        return manual_verdict == "pass"
    raise ScoreRefused(f"unknown check method {method!r}")


def parse_results(text):
    """Parse a Prompt Lab results file into header metadata, T1..T5 outputs, and manual verdicts."""
    lines = [line.rstrip("\r") for line in text.lstrip("\ufeff").splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        raise ScoreRefused("results file is empty")
    hm = RESULTS_HEAD_RE.match(lines[0].strip())
    if not hm:
        raise ScoreRefused("results first line must match '# Lab results · <name> · v<n>'")
    name, version = hm.group(1).strip(), int(hm.group(2))

    section_starts = []
    for idx, line in enumerate(lines[1:], 1):
        if line.strip().startswith("## "):
            section_starts.append((line.strip()[3:].strip(), idx))
    if not section_starts or section_starts[0][0] != "T1":
        raise ScoreRefused("results file must start blocks with '## T1'")

    header_text = "\n".join(lines[1:section_starts[0][1]])
    pm = re.search(r"\bprompt:\s*([0-9a-f]{12})\b", header_text)
    tm = re.search(r"\btests:\s*([0-9a-f]{12})\b", header_text)
    mm = re.search(r"\bmodel:\s*(.+?)(?:\s{2,}date:|\n|$)", header_text)
    dm = re.search(r"\bdate:\s*(\d{4}-\d{2}-\d{2})\b", header_text)
    if not (pm and tm and mm and dm):
        raise ScoreRefused("results header must define prompt, tests, model, and date (YYYY-MM-DD)")
    model = mm.group(1).strip()
    if not model or model.startswith("<"):
        raise ScoreRefused("results header model must be filled")

    seen = set()
    outputs = {}
    manual = {}
    for pos, (sec_name, start_idx) in enumerate(section_starts):
        if sec_name in seen:
            raise ScoreRefused(f"duplicate section '## {sec_name}' in results file")
        seen.add(sec_name)
        end_idx = section_starts[pos + 1][1] if pos + 1 < len(section_starts) else len(lines)
        body_lines = lines[start_idx + 1:end_idx]
        if sec_name in {"T1", "T2", "T3", "T4", "T5"}:
            outputs[sec_name] = "\n".join(body_lines).strip()
        elif sec_name == "manual":
            for mline in body_lines:
                s = mline.strip()
                if not s:
                    continue
                mm_verdict = MANUAL_LINE_RE.match(s)
                if not mm_verdict:
                    raise ScoreRefused(f"invalid manual verdict line: {s!r} (expected 'T<n>: pass|fail <reason>')")
                tid = mm_verdict.group(1).upper()
                manual[tid] = mm_verdict.group(2).lower()
        else:
            raise ScoreRefused(f"unknown section '## {sec_name}' in results file")

    if [s for s, _ in section_starts if s.startswith("T")] != ["T1", "T2", "T3", "T4", "T5"]:
        raise ScoreRefused("results file must have sections ## T1 to ## T5 in order")

    return {
        "name": name,
        "version": version,
        "prompt_hash": pm.group(1),
        "tests_hash": tm.group(1),
        "model": model,
        "date": dm.group(1),
        "outputs": outputs,
        "manual": manual,
        "results_hash": _hash_text(text),
    }


def score_card_results(card, res):
    """Score parsed results against a parsed card. Raises ScoreRefused on hash/version mismatch."""
    if (res["name"], res["version"]) != (card["name"], card["version"]):
        raise ScoreRefused(
            f"results card '{res['name']} v{res['version']}' does not match '{card['name']} v{card['version']}'"
        )
    if res["prompt_hash"] != card["prompt_hash"] or res["tests_hash"] != card["tests_hash"]:
        raise ScoreRefused(
            f"hash mismatch: card has prompt={card['prompt_hash']} tests={card['tests_hash']}, "
            f"results has prompt={res['prompt_hash']} tests={res['tests_hash']}"
        )

    per_test = []
    missing_manual = []
    for t in card["tests"]:
        tid = t["id"]
        out = res["outputs"].get(tid, "")
        passed = True
        for method, arg in t["checks"]:
            if method == "manual" and tid not in res["manual"]:
                missing_manual.append(tid)
                passed = False
                continue
            if not check_one(method, arg, out, manual_verdict=res["manual"].get(tid)):
                passed = False
        per_test.append({"id": tid, "passed": passed and bool(out.strip())})

    return {
        "per_test": per_test,
        "passed_count": sum(1 for r in per_test if r["passed"]),
        "missing_manual": missing_manual,
    }
