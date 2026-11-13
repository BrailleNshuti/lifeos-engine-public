"""lifeos: command line for the LifeOS Engine."""
import argparse
import json
import sys

from . import __version__
from . import lab, mcp, sortcsv
from .delegate import run_delegate
from .ask import ADAPTERS, AskError, Blocked, ToolMissing, provider_status, run_ask, run_review
from .context import build_pack, explain_pack, render_explanation
from .guard import scan_paths, scan_staged, staged_files
from .home import CORE_FILES, HomeError, estimate_tokens, find_home
from .labcard import LabRefused
from .tasks import list_tasks, new_task
from .week import render_markdown, week_numbers

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
    numbers = week_numbers(find_home(args.home), args.week)
    print(json.dumps(numbers, indent=2) if args.json else render_markdown(numbers))
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
    print(f"{out['model']}: {out['reason']}" + (" [dry run, nothing sent]" if args.dry_run else ""))
    if out["text"]:
        print(f"\n{out['text']}\n\n[result appended to {out['path'].relative_to(home)}]")
    if out["flags"]:  # also when the answer is empty, the case CHECK exists for (a dry run has no flags)
        print("CHECK (free, no model): " + "; ".join(out["flags"]))
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
    if getattr(args, "tools", False) or getattr(args, "live", False):
        probe = bool(getattr(args, "live", False))
        print("Providers: (live health probe)" if probe else "Providers: (binary availability)")
        for p in provider_status(probe=probe):
            state = p["status"]
            problems += state not in ("available", "healthy")
            print(f"  {state:<13} {p['model']:<10} ({p['locality']}, {p['detail']})")
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
    doctor.add_argument("--live", action="store_true", help="probe live provider health (local Ollama tags and CLI execution)")
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
