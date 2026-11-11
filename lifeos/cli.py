"""lifeos: command line for the LifeOS Engine."""
import argparse
import json
import sys
from pathlib import Path

from . import __version__
from . import mcp
from .ask import ADAPTERS, AskError, Blocked, run_ask
from .context import build_pack
from .guard import scan_paths, staged_files
from .home import CORE_FILES, HomeError, estimate_tokens, find_home
from .tasks import list_tasks, new_task
from .week import render_markdown, week_numbers

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
    pack, tokens = build_pack(find_home(args.home), args.task, args.budget)
    print(pack)
    print(f"[context pack: about {tokens} tokens, budget {args.budget}]", file=sys.stderr)
    return 0


def cmd_ask(args):
    home = find_home(args.home)
    try:
        result = run_ask(home, args.model, args.task, args.budget, args.dry_run, full=args.full)
    except Blocked as error:
        print(f"lifeos: BLOCKED. {error}", file=sys.stderr)
        return 1
    except AskError as error:
        print(f"lifeos: {error}", file=sys.stderr)
        return 3
    if args.dry_run:
        print(result[0])
        print(f"[dry run: about {result[1]} tokens, nothing sent]", file=sys.stderr)
    else:
        print(f"{args.model} answered; result appended to {result.relative_to(home)}")
    return 0


def cmd_mcp(args):
    home = find_home(args.home)
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    mcp.serve(home, sys.stdin, sys.stdout)
    return 0


def cmd_guard(args):
    paths = staged_files() if args.staged else args.paths
    results = scan_paths(paths)
    blocked = 0
    for path, findings in results:
        for line, severity, kind, excerpt in findings:
            blocked += severity == "BLOCK"
            print(f"{severity:5} {path}:{line}  {kind}  {excerpt}")
    if blocked:
        print(f"\nBlocked: {blocked} finding(s) that must never enter a repo. Remove them, or mark a false alarm "
              f"with 'lifeos-guard: allow' on that line.", file=sys.stderr)
        return 1
    print(f"guard ok: {len(paths)} file(s) checked", file=sys.stderr)
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
    for name in ("ledger.csv", "proofs.csv"):
        if not (home / "logs" / name).exists():
            print(f"  missing   logs/{name}")
            problems += 1
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
    ctx.set_defaults(func=cmd_context)

    ask = sub.add_parser("ask", help="send a task's context pack to another model and write the answer back")
    ask.add_argument("model", choices=sorted(ADAPTERS))
    ask.add_argument("task", help="task id or prefix, for example T-261116")
    ask.add_argument("--budget", type=int, default=6000)
    ask.add_argument("--full", action="store_true", help="also send now.md and me.md (default: task and rules only)")
    ask.add_argument("--dry-run", action="store_true", help="show the pack and token cost; send nothing")
    ask.set_defaults(func=cmd_ask)

    serve = sub.add_parser("mcp", help="run a local MCP server so chat apps can read and write task files")
    serve.set_defaults(func=cmd_mcp)

    guard = sub.add_parser("guard", help="block class C data before it enters a repo")
    guard.add_argument("paths", nargs="*")
    guard.add_argument("--staged", action="store_true", help="check the files staged for commit")
    guard.set_defaults(func=cmd_guard)

    doctor = sub.add_parser("doctor", help="check the data repo and the token cost of its core files")
    doctor.set_defaults(func=cmd_doctor)
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
