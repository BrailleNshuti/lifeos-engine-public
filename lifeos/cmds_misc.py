"""Command handlers moved out of cli.py (it has a size budget). Same code, same behaviour; cli.py re-exports them."""
import datetime as dt
import json
from pathlib import Path
import sys
from . import vocab, lab, seats, sortcsv, study
from .check import QUOTE_MIN_SOURCE, quote_report, task_check_inputs
from .ask import PROVIDERS, AskError, ToolMissing, provider_status
from .guard import scan_paths, scan_staged, staged_files
from .home import CORE_FILES, HomeError, estimate_tokens, find_home
from .labcard import LabRefused
from .store import append_run_record, new_run_id, read_run_records, utc_now_iso

CORE_TOKEN_CAP = 2000
LINE_LIMITS = {"rules.md": 60, "me.md": 15, "now.md": 60, "CLAUDE.md": 60, "AGENTS.md": 40}


def cmd_study(args):
    home = find_home(args.home)
    if args.study_action == "sources":
        rows = study.list_sources(home)
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            for row in rows:
                print(f"{row['subject']:<18} {row['words']:>6} words  {row['path']}  ({row['sha256'][:10]})")
        return 0
    if args.study_action == "import":
        source_path = Path(args.file)
        source = source_path.read_text(encoding="utf-8")
        title = args.title or source_path.stem
        target = study.save_note(home, title, args.subject, source, source_url=args.source_url)
        print(target.relative_to(home).as_posix())
        return 0
    if args.study_action == "bank":
        target = study.write_question_bank(home, args.source, overwrite=args.overwrite)
        print(target.relative_to(home).as_posix())
        return 0
    if args.study_action == "curricula":
        print(json.dumps(study.list_curricula(home), ensure_ascii=False, indent=2))
        return 0
    if args.study_action == "refresh":
        print(json.dumps(study.refresh_question_banks(home, curriculum_id=args.curriculum or ""), ensure_ascii=False))
        return 0
    if args.study_action == "gaps":
        print(json.dumps(study.study_snapshot(home).get("gaps", []), ensure_ascii=False, indent=2))
        return 0
    if args.study_action == "verify":
        result = study.set_question_trust(home, args.bank, args.question, args.trust)
        print(json.dumps(result))
        return 0
    if args.study_action == "attempt":
        result = study.record_attempt(home, args.question, args.rating, elapsed_seconds=args.seconds)
        print(json.dumps(result))
        return 0
    if args.study_action == "exam":
        result = study.compose_exam(
            home, title=args.title, subject=args.subject or "", count=args.count, minutes=args.minutes,
        )
        print(json.dumps({**result, "exam_path": result["exam_path"].relative_to(home).as_posix(),
                          "key_path": result["key_path"].relative_to(home).as_posix()}))
        return 0
    return 2


def cmd_lab(args):
    try:
        home = find_home(args.home)
    except HomeError:
        home = None
    try:
        if args.lab_action == "check":
            info = lab.check_card(home, args.card)
            c = info["card"]
            print(
                f"ok  {c['name']} v{c['version']}  prompt:{c['prompt_hash']}  "
                f"tests:{c['tests_hash']}  ~{info['tokens']} tokens/run"
            )
            return 0
        if args.lab_action == "pack":
            info = lab.pack_card(home, args.card, filled=args.filled, results_out=args.results)
            print(info["pack"], end="")
            if args.results:
                print(f"[results template written to {args.results}]", file=sys.stderr)
            return 0
        if args.lab_action == "score":
            out = lab.score_results(home, args.card, args.results, dry_run=args.dry_run)
            for r in out["per_test"]:
                verdict = "pass" if r["passed"] else "fail"
                print(f"  {r['id']}: {verdict}")
            print(f"{out['passed_count']}/5  ({out['proof_text']})")
            if out["prior_scores"]:
                print(f"earlier runs: {', '.join(out['prior_scores'])}")
            if out["same_tests_diff_prompt"]:
                print("same tests as an earlier prompt version: not independent evidence")
            print(out["score_line"])
            return 0
    except LabRefused as error:
        print(f"lifeos lab: refused ({error})", file=sys.stderr)
        return 1
    return 2


def _print_provider(row):
    print(f"  {row['status']:<13} {row['model']:<10} ({row['locality']}, {row['detail']})", flush=True)


def _record_rest(home, row):
    """Save a probe that hit a usage limit, so the seat table rests it. Never spends tokens, never raises."""
    now = dt.datetime.now(dt.timezone.utc)
    try:
        saved = append_run_record(home, {
            "run_id": new_run_id(now.date()), "date": now.date().isoformat(), "command": "smoke",
            "model": row["model"], "status": "failed", "tokens": 0, "error": row["error"],
            "started_at": utc_now_iso(), "finished_at": utc_now_iso(),
        })
    except Exception:
        saved = None
    if saved is None:
        print(f"  not saved: {row['model']} is resting but logs/runs.jsonl could not be written", flush=True)


def _doctor_providers(home, args):
    """Print the provider block. Return (problems, None), or (0, exit_code) when the probe must stop."""
    smoke = bool(getattr(args, "smoke", False))
    probe = bool(getattr(args, "live", False)) or smoke
    only = {name.strip() for name in str(getattr(args, "only", "") or "").split(",") if name.strip()}
    unknown = sorted(only - set(PROVIDERS))
    if unknown:
        print(f"lifeos: unknown seat {', '.join(unknown)}; choose from {', '.join(sorted(PROVIDERS))}", file=sys.stderr)
        return 0, 2
    title = "authenticated smoke probe" if smoke else "live health probe" if probe else "binary availability"
    print(f"Providers: ({title})")
    callbacks = {}
    skip = None
    if smoke:
        print("  One tiny message per cloud seat; seats that are resting are not called.")
        skip = seats.pressure(read_run_records(home), dt.datetime.now(dt.timezone.utc))
        callbacks = {"on_start": lambda name: print(f"  probing {name} ...", file=sys.stderr, flush=True)}

        def on_row(row):
            _print_provider(row)
            if row["status"] == "resting" and row.get("error"):
                _record_rest(home, row)
        callbacks["on_row"] = on_row
    try:
        rows = provider_status(probe=probe, smoke=smoke, only=only or None, skip=skip, **callbacks)
    except KeyboardInterrupt:
        print("lifeos: stopped; the seats above were already checked.", file=sys.stderr)
        return 0, 130
    if not smoke:
        for row in rows:
            _print_provider(row)
    resting = sum(row["status"] == "resting" for row in rows)
    if resting:
        print(f"  {resting} seat(s) resting: not a fault, they reopen at the time shown.")
    return sum(row["status"] not in _OK_STATES for row in rows), None


def cmd_doctor(args):
    home = find_home(args.home)
    problems, total = 0, 0
    print(f"LifeOS home: {home}")
    for name in (*CORE_FILES, "CLAUDE.md", "AGENTS.md"):
        path = home / name
        if not path.exists():
            print(f"  missing   {name}")
            problems += name in CORE_FILES
            continue
        text = path.read_text(encoding="utf-8")
        lines, tokens = len(text.splitlines()), estimate_tokens(text)
        total += tokens if name in CORE_FILES else 0
        limit = LINE_LIMITS.get(name)
        flag = "too long" if limit and lines > limit else "ok"
        problems += flag != "ok"
        print(f"  {flag:<9} {name:<10} {lines:>3} lines  ~{tokens} tokens")
    print(f"Always-loaded core: ~{total} tokens per conversation that reads rules, me and now.")
    if total > CORE_TOKEN_CAP:
        print(f"  too big   core is ~{total} tokens, over the {CORE_TOKEN_CAP}-token cap. Trim rules, me or now.")
        problems += 1
    for name in ("ledger.csv", "proofs.csv"):
        if not (home / "logs" / name).exists():
            print(f"  missing   logs/{name}")
            problems += 1
    if getattr(args, "tools", False) or getattr(args, "live", False) or getattr(args, "smoke", False):
        found, stop = _doctor_providers(home, args)
        if stop is not None:
            return stop
        problems += found
    print("doctor: ok" if not problems else f"doctor: {problems} thing(s) to fix")
    return 0 if not problems else 1


def cmd_vocab(args):
    home = find_home(args.home)
    try:
        if args.vocab_action == "add":
            vocab.add(home, args.word, args.meaning, args.example)
            print(f"added: {args.word}")
        elif args.vocab_action == "answer":
            vocab.answer(home, args.word, args.result == "good")
            print(f"{args.word}: {args.result}")
        else:
            words = vocab.due(home)[:args.count]
            if not words:
                print("Nothing due. Add words from your own day: lifeos vocab add \"die Wohnung\" \"the flat\"")
            for w in words:
                print(f"{w['word']}" + (f"  = {w['meaning']}" if args.reveal else "") + (f"\n   {w['example']}" if args.reveal and w["example"] else ""))
    except vocab.VocabError as err:
        print(f"lifeos: {err}", file=sys.stderr)
        return 2
    return 0


def cmd_guard(args):
    paths = staged_files() if args.staged else args.paths
    skipped = []
    results = scan_staged(paths, skipped) if args.staged else scan_paths(paths, skipped)
    blocked = 0
    for path, findings in results:
        for line, severity, kind, excerpt in findings:
            blocked += severity == "BLOCK"
            print(f"{severity:5} {path}:{line}  {kind}  {excerpt}")
    if blocked:
        print(f"\nBlocked: {blocked} finding(s) that must never enter a repo. Remove them, or mark a false alarm "
              f"with 'lifeos-guard: allow' on that line.", file=sys.stderr)
        return 1
    note = f", {len(skipped)} skipped (missing, binary or over 1 MB)" if skipped else ""
    print(f"guard ok: {len(paths) - len(skipped)} file(s) checked{note}", file=sys.stderr)
    return 0


_OK_STATES = ("available", "healthy", "cli_healthy", "resting")


def cmd_sort_csv(args):
    cats = [c.strip() for c in args.categories.split(",") if c.strip()] if args.categories else None
    try:
        sortcsv.require_local()
        info = sortcsv.sort_csv(args.file, args.out, args.column, cats)
    except sortcsv.Refused as error:
        print(f"lifeos: {error}", file=sys.stderr)
        return 1
    except ToolMissing as error:
        print(f"lifeos: {error}", file=sys.stderr)
        return 2
    except AskError as error:
        print(f"lifeos: {error}", file=sys.stderr)
        return 3
    print(f"sorted {info['rows']} rows -> {info['out']} (rules: {info['by_rule']}, local model: {info['by_model']}, "
          f"to check: {info['flagged']}). Open the file and review rows where lifeos_check is 'yes'.")
    return 0



def cmd_verify_quotes(args):
    from .context import task_file
    from .delegate import last_result
    home = find_home(args.home)
    try:
        path = task_file(home, args.task)
    except (ValueError, FileNotFoundError) as err:
        print(f"lifeos: {err}", file=sys.stderr)
        return 2
    source = task_check_inputs(path)[1]
    found, missing = quote_report(last_result(path), source)
    if not found and not missing:
        print("No quoted lines (25 characters or more) in the latest answer.")
        return 0
    print(f"{len(found)} of {len(found) + len(missing)} quoted lines are in the task context.")
    for line in missing:
        print(f"  NOT FOUND: {line[:100]}")
    if len(source) < QUOTE_MIN_SOURCE:
        print("The task context is short: a seat that fetched its own pages quotes text that is not here. Check those lines at their source.")
    return 1 if missing else 0
