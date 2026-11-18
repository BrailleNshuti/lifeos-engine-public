"""lifeos: command line for the LifeOS Engine."""
import argparse
import datetime as dt
import json
from pathlib import Path
import sys

from . import __version__
from . import bakeoff, canary, cockpit, exam, governor, kaizen, lab, log, mcp, replay, router, runs, seats, showcase, sortcsv, study, verify
from .delegate import run_delegate
from .ask import ADAPTERS, MINIMAL, PROVIDERS, AskError, Blocked, ToolMissing, provider_status, run_ask, run_review
from .context import build_pack, explain_pack, render_explanation
from .guard import scan_paths, scan_staged, staged_files
from .home import CORE_FILES, HomeError, estimate_tokens, find_home
from .labcard import LabRefused
from .store import append_run_record, new_run_id, read_run_records, utc_now_iso
from .tasks import list_tasks, new_task
from .week import build_redteam_pack, draft_weekly_review, render_markdown, week_numbers

CORE_TOKEN_CAP = 2000
LINE_LIMITS = {"rules.md": 60, "me.md": 15, "now.md": 60, "CLAUDE.md": 60, "AGENTS.md": 40}


def cmd_task(args):
    home = find_home(args.home)
    if args.action == "new":
        path = new_task(home, " ".join(args.sentence), route=args.route, level=args.level, due=args.due or "")
        print(path.relative_to(home))
        print("Next: write the done_when line yourself.")
    else:
        for t in list_tasks(home, args.status):
            print(f"{t['id']:<40} {t['status']:<7} {t['due']:<11} {t['goal']}")
    return 0


def cmd_week(args):
    home = find_home(args.home)
    if getattr(args, "draft", False):
        target = draft_weekly_review(home, args.week)
        print(target.relative_to(home))
        return 0
    if getattr(args, "redteam", False):
        print(build_redteam_pack(home, args.week), end="")
        return 0
    numbers = week_numbers(home, args.week)
    print(json.dumps(numbers, indent=2) if args.json else render_markdown(numbers))
    return 0


def cmd_log(args):
    home = find_home(args.home)
    if args.log_action == "proof":
        line = log.log_proof(home, args.area, args.proof, args.link, date=args.date)
    elif args.log_action == "ledger":
        line = log.log_ledger(home, args.task, args.model, args.minutes, args.note, date=args.date)
    elif args.log_action == "health":
        line = log.log_health(home, args.sleep, args.gym, args.energy, note=args.note, date=args.date)
    elif args.log_action == "hours":
        line = log.log_hours(home, args.area, args.hours, note=args.note, date=args.date)
    else:
        return 2
    print(line)
    return 0


def cmd_runs(args):
    home = find_home(args.home)
    summary = runs.summarize_runs(home, status=args.status, model=args.model, task=args.task, limit=args.limit)
    print(json.dumps(summary, indent=2) if args.json else runs.render_runs(summary))
    return 0


def cmd_verify(args):
    result = verify.verify_chain(find_home(args.home), anchor=args.anchor)
    print(json.dumps(result, indent=2) if args.json else verify.render(result))
    return 0 if result["ok"] and result["anchor_found"] is not False else 1


def cmd_replay(args):
    try:
        out = replay.replay_run(find_home(args.home), args.run_id)
    except replay.ReplayError as err:
        print(f"lifeos: {err}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2) if args.json else replay.render(out))
    return 0 if out["identical"] else (2 if not out["supported"] else 1)


def cmd_canary(args):
    g, o = canary.guard_score(), canary.outbound_check()
    print(json.dumps({"guard": g, "outbound": o}, indent=2) if args.json else canary.render(g, o))
    return 0 if not g["misses"] and not g["benign_flagged"] and o["ok"] else 1


def cmd_kaizen(args):
    home = find_home(args.home)
    if getattr(args, "draft", False):
        target = kaizen.draft_system_health(home, month=args.month)
        print(target.relative_to(home))
        return 0
    report = kaizen.system_health(home, month=args.month)
    print(json.dumps(report, indent=2) if args.json else kaizen.render_system_health(report), end="" if not args.json else "\n")
    return 0


def cmd_route(args):
    home = find_home(args.home)
    decision = router.evaluate_route(home, " ".join(args.target), tier=args.tier, full=args.full)
    print(json.dumps(decision, indent=2) if args.json else router.render_route(decision))
    return 1 if decision["blocked"] else 0


def cmd_cockpit(args):
    home = find_home(args.home)
    if getattr(args, "serve", False):
        print(f"LifeOS Cockpit serving on http://127.0.0.1:{args.port}/#learning", file=sys.stderr)
        cockpit.serve_cockpit(home, port=args.port)
        return 0
    target = cockpit.export_cockpit(home, out_path=args.export)
    try:
        print(target.relative_to(home))
    except ValueError:
        print(target)
    return 0


def cmd_exam(args):
    home = find_home(args.home)
    if getattr(args, "score_skill", None) is not None:
        res = exam.record_exam_score(home, args.score_skill, args.score_pct, proof_link=args.link or "reviews/exam.md")
        print(json.dumps(res))
        return 0
    if getattr(args, "draft", False):
        target = exam.write_exam_draft(home, month=args.month, module=args.module, overwrite=args.overwrite)
        print(target.relative_to(home))
        return 0
    print(exam.generate_monthly_exam(home, month=args.month, module=args.module))
    return 0


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


def cmd_bakeoff(args):
    home = find_home(args.home)
    if getattr(args, "draft", False):
        target = bakeoff.write_bakeoff(
            home, quarter=args.quarter, task_type=args.task_type,
            model_a=args.model_a, model_b=args.model_b, scores_json=args.scores, overwrite=args.overwrite,
        )
        print(target.relative_to(home))
        return 0
    scores = json.loads(args.scores) if args.scores else None
    print(bakeoff.render_bakeoff_card(args.quarter or "2026-Q4", args.task_type, model_a=args.model_a, model_b=args.model_b, scores=scores))
    return 0


def cmd_showcase(args):
    home = find_home(args.home)
    if getattr(args, "draft", False):
        target = showcase.write_weekly_post(home, week=args.week, overwrite=args.overwrite)
        print(target.relative_to(home))
        return 0
    print(showcase.generate_weekly_post(home, week=args.week))
    return 0


def cmd_context(args):
    home = find_home(args.home)
    if getattr(args, "explain", False):
        print(render_explanation(explain_pack(home, args.task, args.budget)))
        return 0
    pack, tokens = build_pack(home, args.task, args.budget)
    print(pack)
    print(f"[context pack: about {tokens} tokens, budget {args.budget}]", file=sys.stderr)
    return 0


def cmd_ask(args):
    home = find_home(args.home)
    try:
        estimate = build_pack(home, args.task, args.budget, task_first=True, names=None if args.full else MINIMAL)[1]
        gate = governor.check(home, args.model, estimate)
    except (ValueError, FileNotFoundError, OSError):
        gate = None  # the real run below reports a bad task or budget with its own message
    if gate is not None:
        print(governor.render(gate), file=sys.stderr)
        if not gate["allowed"] and not args.dry_run and not getattr(args, "force", False):
            print("lifeos: nothing was sent. Use --force to send anyway, or wait for the reset.", file=sys.stderr)
            return 4
    try:
        result = run_ask(
            home, args.model, args.task, args.budget, args.dry_run,
            full=args.full, run_id=getattr(args, "run_id", None),
        )
    except Blocked as error:
        print(f"lifeos: BLOCKED. {error}", file=sys.stderr)
        return 1
    except ToolMissing as error:
        print(f"lifeos: {error}", file=sys.stderr)
        return 2
    except AskError as error:
        print(f"lifeos: {error}", file=sys.stderr)
        return 3
    if args.dry_run:
        print(result[0])
        print(f"[dry run: about {result[1]} tokens, nothing sent]", file=sys.stderr)
    else:
        print(f"{args.model} answered; result appended to {result.relative_to(home)}")
    return 0


def cmd_delegate(args):
    home = find_home(args.home)
    try:
        out = run_delegate(home, args.task, args.model, args.budget, args.full, dry_run=args.dry_run)
    except Blocked as error:
        print(f"lifeos: BLOCKED. {error}", file=sys.stderr)
        return 1
    except ToolMissing as error:
        print(f"lifeos: {error}", file=sys.stderr)
        return 2
    except AskError as error:
        print(f"lifeos: {error}", file=sys.stderr)
        return 3
    chain = " -> ".join(out.get("chain") or [])
    print(f"{out['model']}: {out['reason']}" + (f" · chain {chain}" if chain else "")
          + (" [dry run, nothing sent]" if args.dry_run else ""))
    for note in out.get("notes") or []:
        print(f"NOTE {note}")
    if out["text"]:
        print(f"\n{out['text']}\n\n[result appended to {out['path'].relative_to(home)}]")
    if out["flags"]:  # also when the answer is empty, the case CHECK exists for (a dry run has no flags)
        print("CHECK (free, no model): " + "; ".join(out["flags"]))
    return 0


def cmd_seats(args):
    home = find_home(args.home)
    rows = seats.table(read_run_records(home), dt.datetime.now(dt.timezone.utc))
    print(json.dumps(rows, indent=2) if args.json else seats.render_table(rows))
    return 0


def cmd_review(args):
    home = find_home(args.home)
    revs = [r.strip() for r in args.reviewers.split(",") if r.strip()]
    try:
        out = run_review(
            home, args.task, reviewers=revs, budget=args.budget, dry_run=args.dry_run,
            repo=getattr(args, "repo", None), commit=getattr(args, "commit", "HEAD"),
            run_id=getattr(args, "run_id", None),
        )
    except Blocked as error:
        print(f"lifeos: BLOCKED. {error}", file=sys.stderr)
        return 1
    except ToolMissing as error:
        print(f"lifeos: {error}", file=sys.stderr)
        return 2
    except AskError as error:
        print(f"lifeos: {error}", file=sys.stderr)
        return 3
    if args.dry_run:
        print(out["pack"])
        print(f"[dry run: blind review pack ({out['sha256']}) for {', '.join(out['reviewers'])}, ~{out['tokens']} tokens]",
              file=sys.stderr)
        return 0
    commit_note = f", commit {out['commit_sha'][:12]}" if out.get("commit_sha") else ""
    print(f"blind review ({out['group_run_id']}, pack {out['sha256'][:12]}{commit_note}) -> {out['path'].relative_to(home)}")
    for r in out["results"]:
        warn = f" [CHECK: {'; '.join(r['flags'])}]" if r["flags"] else ""
        print(f"  {r['label']} ({r['run_id']}){warn}")
    return 0


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


def cmd_mcp(args):
    home = find_home(args.home)
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    mcp.serve(home, sys.stdin, sys.stdout)
    return 0


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


def build_parser():
    parser = argparse.ArgumentParser(prog="lifeos", description="LifeOS Engine: tasks, weekly numbers, context packs, privacy guard.")
    parser.add_argument("--home", help="LifeOS data repo (default: LIFEOS_HOME or the current folder)")
    parser.add_argument("--version", action="version", version=f"lifeos {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    task = sub.add_parser("task", help="create or list task files")
    task_sub = task.add_subparsers(dest="action", required=True)
    new = task_sub.add_parser("new", help="create a task file from one sentence")
    new.add_argument("sentence", nargs="+")
    new.add_argument("--route", default="Claude Code -> Codex review")
    new.add_argument("--level", default="L2", choices=["L0", "L1", "L2", "L3"])
    new.add_argument("--due")
    lst = task_sub.add_parser("list", help="list task files")
    lst.add_argument("--status", choices=["inbox", "doing", "done"])
    task.set_defaults(func=cmd_task)

    week = sub.add_parser("week", help="numbers for the weekly review, from the logs")
    week.add_argument("--week", help="ISO week such as 2026-W47 (default: this week)")
    week.add_argument("--json", action="store_true")
    week.add_argument("--draft", action="store_true", help="write reviews/<week>.md pre-filled with log numbers (never overwrites)")
    week.add_argument("--redteam", action="store_true", help="print a facts-only Red-Team pack for item 6 of the weekly review")
    week.set_defaults(func=cmd_week)

    ctx = sub.add_parser("context", help="print a context pack for another model, within a token budget")
    ctx.add_argument("task", nargs="?", help="task id or prefix, for example T-261116")
    ctx.add_argument("--budget", type=int, default=6000)
    ctx.add_argument("--explain", action="store_true", help="show why each file was included, trimmed or excluded, plus sha256")
    ctx.set_defaults(func=cmd_context)

    ask = sub.add_parser("ask", help="send a task's context pack to another model and write the answer back")
    ask.add_argument("model", choices=sorted(ADAPTERS))
    ask.add_argument("task", help="task id or prefix, for example T-261116")
    ask.add_argument("--budget", type=int, default=6000)
    ask.add_argument("--full", action="store_true", help="also send now.md and me.md (default: task and rules only)")
    ask.add_argument("--run-id", help="explicit run_id for idempotent retry")
    ask.add_argument("--dry-run", action="store_true", help="show the pack and token cost; send nothing")
    ask.add_argument("--force", action="store_true", help="send even if the budget governor holds the call")
    ask.set_defaults(func=cmd_ask)

    dele = sub.add_parser("delegate", help="let LifeOS pick the best-fitting model for a task, run it, and print the answer")
    dele.add_argument("task", help="task id or prefix, for example T-261116")
    dele.add_argument("--model", choices=sorted(ADAPTERS), help="override the pick")
    dele.add_argument("--budget", type=int, default=6000)
    dele.add_argument("--full", action="store_true", help="also send now.md and me.md")
    dele.add_argument("--dry-run", action="store_true", help="show which model would take it; send nothing")
    dele.set_defaults(func=cmd_delegate)

    rev = sub.add_parser("review", help="run an independent blind review (rule 7) across multiple models")
    rev.add_argument("task", help="task id or prefix, for example T-261116")
    rev.add_argument("--reviewers", default="codex,claude", help="comma-separated reviewer models (default: codex,claude)")
    rev.add_argument("--repo", help="git repository path to inspect and mount in an isolated read-only worktree")
    rev.add_argument("--commit", default="HEAD", help="git commit or ref to review when --repo is set (default: HEAD)")
    rev.add_argument("--run-id", help="explicit parent run_id for idempotent retry")
    rev.add_argument("--budget", type=int, default=6000)
    rev.add_argument("--dry-run", action="store_true", help="show the blind review pack and hash; send nothing")
    rev.set_defaults(func=cmd_review)

    srt = sub.add_parser("sort-csv", help="add a spending category to a bank CSV, fully local (Ollama), never in a repo")
    srt.add_argument("file")
    srt.add_argument("--out", help="default: <file>.sorted.csv beside the input")
    srt.add_argument("--column", help="the text column (default: found by name)")
    srt.add_argument("--categories", help="comma separated; default: groceries,rent,transport,...")
    srt.set_defaults(func=cmd_sort_csv)

    serve = sub.add_parser("mcp", help="run a local MCP server so chat apps can read and write task files")
    serve.set_defaults(func=cmd_mcp)

    guard = sub.add_parser("guard", help="block class C data before it enters a repo")
    guard.add_argument("paths", nargs="*")
    guard.add_argument("--staged", action="store_true", help="check the files staged for commit")
    guard.set_defaults(func=cmd_guard)

    doctor = sub.add_parser("doctor", help="check the data repo and the token cost of its core files")
    doctor.add_argument("--tools", action="store_true", help="check binary availability of local and remote model CLIs")
    doctor.add_argument("--live", action="store_true", help="probe live provider health (local Ollama tags and CLI --version)")
    doctor.add_argument("--smoke", action="store_true", help="run an authenticated live smoke request per provider")
    doctor.add_argument("--only", help="with --smoke or --live: probe only these seats, comma separated (saves usage)")
    doctor.set_defaults(func=cmd_doctor)

    lab_p = sub.add_parser("lab", help="Prompt Lab: validate cards, pack test inputs, and score results offline")
    lab_sub = lab_p.add_subparsers(dest="lab_action", required=True)
    lab_chk = lab_sub.add_parser("check", help="validate a prompt card and print its prompt and tests hashes")
    lab_chk.add_argument("card", help="card path or name in prompts/cards/")
    lab_pck = lab_sub.add_parser("pack", help="print the card's prompt and five test inputs")
    lab_pck.add_argument("card", help="card path or name in prompts/cards/")
    lab_pck.add_argument("--filled", action="store_true", help="print five finished prompts instead")
    lab_pck.add_argument("--results", help="write the empty results file with locked hashes (never overwrites)")
    lab_scr = lab_sub.add_parser("score", help="score a results file offline and log one proof row")
    lab_scr.add_argument("card", help="card path or name in prompts/cards/")
    lab_scr.add_argument("results", help="results file path")
    lab_scr.add_argument("--dry-run", action="store_true", help="score without writing to logs/proofs.csv")
    lab_p.set_defaults(func=cmd_lab)

    log_p = sub.add_parser("log", help="append a validated row to proofs.csv, ledger.csv, health.csv, or hours.csv")
    log_sub = log_p.add_subparsers(dest="log_action", required=True)
    log_prf = log_sub.add_parser("proof", help="append a proof row to logs/proofs.csv")
    log_prf.add_argument("--area", required=True)
    log_prf.add_argument("--proof", required=True)
    log_prf.add_argument("--link", required=True)
    log_prf.add_argument("--date", help="YYYY-MM-DD (default: today)")
    log_ldg = log_sub.add_parser("ledger", help="append a ledger row to logs/ledger.csv")
    log_ldg.add_argument("--task", required=True)
    log_ldg.add_argument("--model", required=True)
    log_ldg.add_argument("--minutes", required=True)
    log_ldg.add_argument("--note", required=True)
    log_ldg.add_argument("--date", help="YYYY-MM-DD (default: today)")
    log_hlt = log_sub.add_parser("health", help="append a daily health row to logs/health.csv")
    log_hlt.add_argument("--sleep", required=True)
    log_hlt.add_argument("--gym", required=True)
    log_hlt.add_argument("--energy", required=True)
    log_hlt.add_argument("--note", default="")
    log_hlt.add_argument("--date", help="YYYY-MM-DD (default: today)")
    log_hrs = log_sub.add_parser("hours", help="append a study/work hours row to logs/hours.csv")
    log_hrs.add_argument("--area", required=True)
    log_hrs.add_argument("--hours", required=True)
    log_hrs.add_argument("--note", default="")
    log_hrs.add_argument("--date", help="YYYY-MM-DD (default: today)")
    log_p.set_defaults(func=cmd_log)

    runs_p = sub.add_parser("runs", help="inspect execution run records and summary analytics from logs/runs.jsonl")
    runs_p.add_argument("--status", help="filter by terminal status (ok, failed, timeout, blocked, tool_missing, partial)")
    runs_p.add_argument("--model", help="filter by provider model name")
    runs_p.add_argument("--task", help="filter by task id or prefix")
    runs_p.add_argument("--limit", type=int, default=20, help="max recent records to display (default: 20)")
    runs_p.add_argument("--json", action="store_true", help="output structured JSON summary and records")
    runs_p.set_defaults(func=cmd_runs)

    ver_p = sub.add_parser("verify", help="prove logs/runs.jsonl was not edited, reordered or cut (hash chain)")
    ver_p.add_argument("--anchor", help="a head hash you saved earlier; checks the log still contains that exact state")
    ver_p.add_argument("--json", action="store_true", help="output structured JSON")
    ver_p.set_defaults(func=cmd_verify)

    rpl_p = sub.add_parser("replay", help="rebuild an ask run's context from today's files and prove it is the same input")
    rpl_p.add_argument("run_id")
    rpl_p.add_argument("--json", action="store_true", help="output structured JSON")
    rpl_p.set_defaults(func=cmd_replay)

    can_p = sub.add_parser("canary", help="guard score on generated fake identifiers, and proof ask never sends them")
    can_p.add_argument("--json", action="store_true", help="output structured JSON")
    can_p.set_defaults(func=cmd_canary)

    kzn_p = sub.add_parser("kaizen", help="monthly System Health check (Section 10.3) and 4-week trial audit")
    kzn_p.add_argument("--month", help="YYYY-MM (default: current month)")
    kzn_p.add_argument("--draft", action="store_true", help="write reviews/<YYYY-MM>.md without overwriting")
    kzn_p.add_argument("--json", action="store_true", help="output structured JSON health report")
    kzn_p.set_defaults(func=cmd_kaizen)

    rte_p = sub.add_parser("route", help="evaluate the 6-question Section 8.2 routing decision for a task or prompt")
    rte_p.add_argument("target", nargs="+", help="task id (e.g. T-261116) or free-text task description")
    rte_p.add_argument("--tier", help="override 5-tier data classification (PUBLIC, INTERNAL, PERSONAL, SENSITIVE, SECRET)")
    rte_p.add_argument("--full", action="store_true", help="evaluate with me.md and now.md included")
    rte_p.add_argument("--json", action="store_true", help="output structured JSON routing decision")
    rte_p.set_defaults(func=cmd_route)

    seat_p = sub.add_parser("seats", help="show every model seat: 7-day spend against its one limit, rest, and replacement")
    seat_p.add_argument("--json", action="store_true", help="output the seat table as JSON")
    seat_p.set_defaults(func=cmd_seats)

    ckp_p = sub.add_parser("cockpit", help="export or serve the learning-first LifeOS Cockpit (#focus, #library, #recall, #mastery)")
    ckp_p.add_argument("--export", help="output HTML file path (default: <home>/cockpit/index.html)")
    ckp_p.add_argument("--serve", action="store_true", help="run a local HTTP server bound strictly to 127.0.0.1")
    ckp_p.add_argument("--port", type=int, default=8765, help="localhost port for --serve (default: 8765)")
    ckp_p.set_defaults(func=cmd_cockpit)

    std_p = sub.add_parser("study", help="local-first notes, grounded question banks, retrieval practice and exams")
    std_sub = std_p.add_subparsers(dest="study_action", required=True)
    std_src = std_sub.add_parser("sources", help="list indexed Markdown/text learning sources")
    std_src.add_argument("--json", action="store_true")
    std_imp = std_sub.add_parser("import", help="copy a UTF-8 Markdown/text file into the guarded source library")
    std_imp.add_argument("file")
    std_imp.add_argument("--title")
    std_imp.add_argument("--subject", default="general")
    std_imp.add_argument("--source-url", default="")
    std_bnk = std_sub.add_parser("bank", help="create a grounded draft question bank from one learning source")
    std_bnk.add_argument("source", help="LifeOS-relative source path, for example learning/sources/python.md")
    std_bnk.add_argument("--overwrite", action="store_true")
    std_cur = std_sub.add_parser("curricula", help="list ordered learning journeys and their source steps")
    std_ref = std_sub.add_parser("refresh", help="create missing grounded banks for curriculum sources")
    std_ref.add_argument("--curriculum", help="optional curriculum id")
    std_sub.add_parser("gaps", help="show sanitized weak concepts and their remediation sources")
    std_ver = std_sub.add_parser("verify", help="record human trust state for one grounded question")
    std_ver.add_argument("bank")
    std_ver.add_argument("question")
    std_ver.add_argument("--trust", choices=study.TRUST_STATES, default="verified")
    std_att = std_sub.add_parser("attempt", help="record a verified retrieval attempt and next-review interval")
    std_att.add_argument("question")
    std_att.add_argument("--rating", choices=study.RATINGS, required=True)
    std_att.add_argument("--seconds", type=int, default=0)
    std_exm = std_sub.add_parser("exam", help="compose a printable exam plus separate key from verified questions")
    std_exm.add_argument("--title", default="Practice Exam")
    std_exm.add_argument("--subject")
    std_exm.add_argument("--count", type=int, default=10)
    std_exm.add_argument("--minutes", type=int, default=60)
    std_p.set_defaults(func=cmd_study)

    exm_p = sub.add_parser("exam", help="generate or score a 60-90 min Monthly No-AI Exam (Section 13.4 & Appendix B8)")
    exm_p.add_argument("--month", help="YYYY-MM (default: current month)")
    exm_p.add_argument("--module", default="CSEBDSDSSE01 · Data Science Software Engineering", help="IU module focus")
    exm_p.add_argument("--draft", action="store_true", help="write reviews/exam-<YYYY-MM>.md")
    exm_p.add_argument("--overwrite", action="store_true", help="overwrite existing exam draft")
    exm_p.add_argument("--score-skill", help="skill name in logs/skills.md to record a graded no-AI exam score")
    exm_p.add_argument("--score-pct", type=int, default=0, help="exam score percentage (0-100); >=80 elevates level to 3")
    exm_p.add_argument("--link", help="proof link for logs/proofs.csv")
    exm_p.set_defaults(func=cmd_exam)

    bkf_p = sub.add_parser("bakeoff", help="generate or score a blind Role Bake-Off scorecard (Section 10.4 & Appendix A8)")
    bkf_p.add_argument("--quarter", help="YYYY-Q1..Q4 (default: current quarter)")
    bkf_p.add_argument("--task-type", default="Decision Memo", help="task category being compared")
    bkf_p.add_argument("--model-a", default="claude")
    bkf_p.add_argument("--model-b", default="chatgpt")
    bkf_p.add_argument("--scores", help="JSON dict of X/Y task scores to unseal winner")
    bkf_p.add_argument("--draft", action="store_true", help="write reviews/bakeoff-<quarter>-<slug>.md")
    bkf_p.add_argument("--overwrite", action="store_true")
    bkf_p.set_defaults(func=cmd_bakeoff)

    shw_p = sub.add_parser("showcase", help="draft a 20-minute Build-in-Public weekly proof post & case study (Section 14.4 / D12)")
    shw_p.add_argument("--week", help="ISO week such as 2026-W46")
    shw_p.add_argument("--draft", action="store_true", help="write reviews/post-<week>.md")
    shw_p.add_argument("--overwrite", action="store_true")
    shw_p.set_defaults(func=cmd_showcase)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (HomeError, FileNotFoundError, ValueError) as error:
        print(f"lifeos: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
