"""Prompt Lab card parser, normaliser, hashes and pack formatter (layer 0, offline, stdlib only)."""
import hashlib
import re

HEADER_RE = re.compile(r"^#\s*Prompt card\s*·\s*(.+?)\s*·\s*v(\d+)\s*·\s*(\d{4}-\d{2}-\d{2})\s*$")
PLACEHOLDER_RE = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")
VAR_LINE_RE = re.compile(r"^\{\{([a-zA-Z0-9_]+)\}\}:\s*(.*)$")
TEST_HEAD_RE = re.compile(r"^T([1-5])(?:\s+(.*))?$")
VALID_METHODS = {"exact", "exact/i", "json", "has", "has/i", "lacks", "lacks/i", "sources", "manual"}


class LabRefused(ValueError):
    """Raised when a Prompt Lab card or results file violates a lab rule."""


def decode_card_bytes(raw):
    """Decode UTF-8, UTF-8-BOM or UTF-16-BOM bytes into text."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def normalise_block(lines):
    """Normalise line endings and trailing horizontal whitespace for stable hashing."""
    cleaned = [line.rstrip(" \t\r") for line in lines]
    while cleaned and not cleaned[0]:
        cleaned.pop(0)
    while cleaned and not cleaned[-1]:
        cleaned.pop()
    return "\n".join(cleaned)


def hash_text(text):
    """Return the 12-hex SHA-256 of normalised lines."""
    norm = normalise_block(text.splitlines())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:12]


def _find_line_index(lines, prefixes, start=0):
    for idx in range(start, len(lines)):
        stripped = lines[idx].strip()
        if any(stripped.startswith(p) for p in prefixes):
            return idx
    return -1


def _extract_label_value(lines, prefix, end):
    for line in lines[:end]:
        s = line.strip()
        if s.startswith(prefix):
            return s[len(prefix):].strip()
    return ""


def _parse_tests_section(lines, declared_inputs):
    """Parse shared {{x}}: inputs and T1..T5 blocks between 'Tests' and 'Pass when:'."""
    t_indices = []
    for idx, line in enumerate(lines):
        m = TEST_HEAD_RE.match(line.strip())
        if m:
            t_indices.append((int(m.group(1)), idx, (m.group(2) or "").strip()))
    if [num for num, _, _ in t_indices] != [1, 2, 3, 4, 5]:
        raise LabRefused("card must have exactly five tests (T1 to T5 in order)")

    shared = {}
    current_var = None
    for line in lines[1:t_indices[0][1]]:
        vm = VAR_LINE_RE.match(line.strip())
        if vm:
            current_var = vm.group(1)
            if current_var not in declared_inputs:
                raise LabRefused(f"shared test input '{{{{{current_var}}}}}' is not declared in Inputs")
            shared[current_var] = [vm.group(2)] if vm.group(2) else []
        elif current_var is not None:
            shared[current_var].append(line.rstrip(" \t\r"))
    shared_vals = {k: "\n".join(v).strip() for k, v in shared.items()}

    tests = []
    for pos, (num, start_idx, title) in enumerate(t_indices):
        end_idx = t_indices[pos + 1][1] if pos + 1 < len(t_indices) else len(lines)
        block = lines[start_idx + 1:end_idx]
        local_vars = {}
        checks = []
        current_var = None
        for raw_line in block:
            s = raw_line.strip()
            vm = VAR_LINE_RE.match(s)
            if vm:
                current_var = vm.group(1)
                if current_var not in declared_inputs:
                    raise LabRefused(f"T{num} input '{{{{{current_var}}}}}' is not declared in Inputs")
                local_vars[current_var] = [vm.group(2)] if vm.group(2) else []
            elif s.startswith("check:"):
                current_var = None
                rest = s[len("check:"):].strip()
                parts = rest.split(None, 1)
                if not parts or parts[0] not in VALID_METHODS or (len(parts) < 2 or not parts[1].strip()):
                    raise LabRefused(f"T{num} has invalid check: line ({s!r})")
                checks.append((parts[0], parts[1].strip()))
            elif s.startswith("pass:"):
                current_var = None
            elif current_var is not None:
                local_vars[current_var].append(raw_line.rstrip(" \t\r"))

        if not checks:
            raise LabRefused(f"T{num} is missing a check: line")
        merged = dict(shared_vals)
        for k, v in local_vars.items():
            merged[k] = "\n".join(v).strip()
        for req in declared_inputs:
            if not merged.get(req):
                raise LabRefused(f"T{num} is missing a value for declared input '{{{{{req}}}}}'")
        tests.append({"id": f"T{num}", "title": title, "values": merged, "checks": checks})
    return shared_vals, tests


def parse_card(text):
    """Parse and validate a Prompt Lab card, returning a dict with prompt_hash and tests_hash."""
    raw_lines = [line.rstrip(" \t\r") for line in text.lstrip("\ufeff").splitlines()]
    lines = [line for idx, line in enumerate(raw_lines) if idx > 0 or line]
    if not lines:
        raise LabRefused("card is empty")
    hm = HEADER_RE.match(lines[0])
    if not hm:
        raise LabRefused("first line must match '# Prompt card · <name> · v<n> · <YYYY-MM-DD>'")
    name, version, date = hm.group(1).strip(), int(hm.group(2)), hm.group(3)

    role_idx = _find_line_index(lines, ("Role and context:",))
    tests_idx = _find_line_index(lines, ("Tests (made-up data):", "Tests:"), start=max(role_idx, 0))
    pass_idx = _find_line_index(lines, ("Pass when:",), start=max(tests_idx, 0))
    safety_idx = _find_line_index(lines, ("Safety check:",), start=max(pass_idx, 0))
    score_idx = _find_line_index(lines, ("Score:",), start=max(safety_idx, 0))
    if min(role_idx, tests_idx, pass_idx, safety_idx) < 0:
        raise LabRefused("card is missing required sections (Role and context, Tests, Pass when, Safety check)")

    goal = _extract_label_value(lines, "Goal:", role_idx)
    used_in = _extract_label_value(lines, "Used in:", role_idx)
    ok_val = _extract_label_value(lines, "OK:", role_idx)
    safety_end = score_idx if score_idx > safety_idx else len(lines)
    safety_val = "\n".join(lines[safety_idx:safety_end])[len("Safety check:"):].strip()

    for label, val in (("Goal", goal), ("Used in", used_in), ("OK", ok_val), ("Safety check", safety_val)):
        if not val or val.startswith("[") or val.startswith("<"):
            raise LabRefused(f"card field '{label}:' must be filled")

    prompt_lines = lines[role_idx:tests_idx]
    tests_lines = lines[tests_idx:safety_idx]
    prompt_text = normalise_block(prompt_lines)
    tests_text = normalise_block(tests_lines)

    inputs_idx = _find_line_index(prompt_lines, ("Inputs (placeholders only):", "Inputs:"))
    rules_idx = _find_line_index(prompt_lines, ("Rules:",), start=max(inputs_idx, 0))
    if inputs_idx < 0 or rules_idx < 0:
        raise LabRefused("prompt part must contain 'Inputs (placeholders only):' and 'Rules:'")
    inputs_block = "\n".join(prompt_lines[inputs_idx:rules_idx])
    declared = []
    for var in PLACEHOLDER_RE.findall(inputs_block):
        if var not in declared:
            declared.append(var)
    if not declared:
        raise LabRefused("Inputs must declare at least one {{placeholder}}")

    for used_var in PLACEHOLDER_RE.findall(prompt_text):
        if used_var not in declared:
            raise LabRefused(f"prompt uses undeclared placeholder '{{{{{used_var}}}}}'")

    shared_vals, parsed_tests = _parse_tests_section( lines[tests_idx:pass_idx], declared)

    return {
        "name": name,
        "version": version,
        "date": date,
        "goal": goal,
        "used_in": used_in,
        "ok": ok_val,
        "safety_check": safety_val,
        "inputs": declared,
        "prompt": prompt_text,
        "tests_raw": tests_text,
        "prompt_hash": hash_text(prompt_text),
        "tests_hash": hash_text(tests_text),
        "shared": shared_vals,
        "tests": parsed_tests,
    }


def format_pack(card, filled=False):
    """Format the card's prompt and five test inputs (never titles, check: or pass: lines)."""
    if not filled:
        blocks = [card["prompt"]]
        for t in card["tests"]:
            lines = [f"## {t['id']}"]
            for var in card["inputs"]:
                lines.append(f"{{{{{var}}}}}: {t['values'][var]}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks) + "\n"

    blocks = []
    for t in card["tests"]:
        rendered = card["prompt"]
        appended = []
        for var in card["inputs"]:
            val = t["values"][var]
            rendered = rendered.replace(f"{{{{{var}}}}}", val)
            appended.append(f"{var}: {val}")
        blocks.append(f"## {t['id']}\n{rendered}\n\n" + "\n".join(appended))
    return "\n\n".join(blocks) + "\n"


def format_results_template(card):
    """Return the empty results template with locked prompt and tests hashes."""
    lines = [
        f"# Lab results · {card['name']} · v{card['version']}",
        f"prompt: {card['prompt_hash']}   tests: {card['tests_hash']}",
        "model: <exact id shown in the console>   date: <YYYY-MM-DD>",
        "settings: <free text, e.g. temperature>   tokens: <in>/<out>",
    ]
    has_manual = False
    for t in card["tests"]:
        lines.append(f"## {t['id']}")
        lines.append("")
        if any(m == "manual" for m, _ in t["checks"]):
            has_manual = True
    if has_manual:
        lines.append("## manual")
        for t in card["tests"]:
            if any(m == "manual" for m, _ in t["checks"]):
                lines.append(f"{t['id']}: <pass|fail reason>")
    return "\n".join(lines) + "\n"
