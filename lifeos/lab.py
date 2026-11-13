"""Prompt Lab commands: check, pack, and score (layer 1, offline, no model calls)."""
import csv
from pathlib import Path

from . import __version__
from .guard import private_patterns, scan_text
from .home import estimate_tokens
from .labcard import LabRefused, decode_card_bytes, format_pack, format_results_template, parse_card
from .labscore import ScoreRefused, parse_results, score_card_results
from .store import append_proof_row, atomic_write_bytes


def resolve_card_path(home, card_arg):
    """Resolve `<card>` as a direct path or a name under `<home>/prompts/cards/`."""
    direct = Path(card_arg)
    if direct.is_file():
        return direct
    if home is not None:
        stem = card_arg[:-3] if card_arg.endswith(".md") else card_arg
        candidate = Path(home) / "prompts" / "cards" / f"{stem}.md"
        if candidate.is_file():
            return candidate
        rel = Path(home) / card_arg
        if rel.is_file():
            return rel
    raise FileNotFoundError(f"card not found: {card_arg}")


def _guard_text(text, label):
    findings = scan_text(text, private_patterns())
    blocks = [f for f in findings if f[1] == "BLOCK"]
    if blocks:
        first = blocks[0]
        raise LabRefused(f"guard blocked {label} at line {first[0]} ({first[2]}: {first[3]})")


def check_card(home, card_arg):
    """Validate a Prompt Lab card, run the privacy guard, and compute token estimate."""
    path = resolve_card_path(home, card_arg)
    text = decode_card_bytes(path.read_bytes())
    _guard_text(text, str(path))
    card = parse_card(text)
    filled_text = format_pack(card, filled=True)
    return {
        "path": path,
        "card": card,
        "tokens": estimate_tokens(filled_text),
    }


def pack_card(home, card_arg, filled=False, results_out=None):
    """Check a card, optionally write the empty results file (never overwriting), and return pack text."""
    info = check_card(home, card_arg)
    card = info["card"]
    if results_out:
        out_path = Path(results_out)
        if out_path.exists():
            raise LabRefused(f"refusing to overwrite existing results file: {out_path}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(out_path, format_results_template(card).encode("utf-8"))
    return {
        "card": card,
        "pack": format_pack(card, filled=filled),
        "tokens": info["tokens"],
    }


def _prior_lab_runs(home, card, model, results_hash):
    """Inspect logs/proofs.csv and logs/lab/ for earlier runs of the same card/version/model or tests_hash."""
    prior_scores = []
    same_tests_diff_prompt = False
    already_logged = False
    if home is None:
        return 1, prior_scores, same_tests_diff_prompt, already_logged

    proofs = Path(home) / "logs" / "proofs.csv"
    prefix = f"{card['name']} v{card['version']};"
    dedupe_key = f"results {results_hash}"
    if proofs.is_file():
        with proofs.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if row.get("area") != "lab":
                    continue
                proof_text = row.get("proof") or ""
                if dedupe_key in proof_text:
                    already_logged = True
                elif proof_text.startswith(prefix) and f"; {model};" in proof_text:
                    parts = [p.strip() for p in proof_text.split(";")]
                    if len(parts) >= 2:
                        prior_scores.append(parts[1])

    lab_dir = Path(home) / "logs" / "lab"
    if lab_dir.is_dir():
        for rfile in sorted(lab_dir.glob("*.md")):
            try:
                other = parse_results(decode_card_bytes(rfile.read_bytes()))
            except Exception:
                continue
            if (
                other["name"] == card["name"]
                and other["tests_hash"] == card["tests_hash"]
                and other["prompt_hash"] != card["prompt_hash"]
            ):
                same_tests_diff_prompt = True
    return len(prior_scores) + 1, prior_scores, same_tests_diff_prompt, already_logged


def score_results(home, card_arg, results_arg, dry_run=False):
    """Check card and results file, score all 5 tests offline, and log one proof row unless dry_run."""
    info = check_card(home, card_arg)
    card = info["card"]
    res_path = Path(results_arg)
    if not res_path.is_file() and home is not None and (Path(home) / results_arg).is_file():
        res_path = Path(home) / results_arg
    if not res_path.is_file():
        raise FileNotFoundError(f"results file not found: {results_arg}")

    res_text = decode_card_bytes(res_path.read_bytes())
    _guard_text(res_text, str(res_path))
    try:
        res = parse_results(res_text)
        scored = score_card_results(card, res)
    except ScoreRefused as err:
        raise LabRefused(str(err)) from err
    if scored["missing_manual"]:
        missing = ", ".join(scored["missing_manual"])
        raise LabRefused(f"missing manual verdict for {missing} in ## manual")

    run_num, prior_scores, same_tests_diff_prompt, already_logged = _prior_lab_runs(
        home, card, res["model"], res["results_hash"]
    )
    k = scored["passed_count"]
    proof_text = (
        f"{card['name']} v{card['version']}; {k}/5; {res['model']}; "
        f"run {run_num}; typed by hand; results {res['results_hash']}; lifeos {__version__}"
    )

    logged = False
    if not dry_run and home is not None and not already_logged:
        try:
            rel_link = res_path.resolve().relative_to(Path(home).resolve()).as_posix()
        except ValueError:
            rel_link = res_path.as_posix()
        logged = append_proof_row(
            Path(home) / "logs" / "proofs.csv",
            res["date"],
            "lab",
            proof_text,
            rel_link,
            dedupe_token=f"results {res['results_hash']}",
        )

    return {
        "card": card,
        "results": res,
        "per_test": scored["per_test"],
        "passed_count": k,
        "run_num": run_num,
        "prior_scores": prior_scores,
        "same_tests_diff_prompt": same_tests_diff_prompt,
        "proof_text": proof_text,
        "logged": logged,
        "score_line": f"Score: v{card['version']} {k}/5 ({res['model']}, {res['date']})",
    }
