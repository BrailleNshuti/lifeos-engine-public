"""Refresh the cockpit's data in one step: run `lifeos dash-export` into a folder and print what to hand over.

Usage: python scripts/refresh_cockpit.py [--out DIR] [--home DIR]
Standard library only. No model is called and nothing is uploaded. The files hold task goals and rating notes, so the folder
is created next to your home folder, never inside this repo, and the last line reminds you to load them only into a page
only you can open. Exit code 0 when the export worked.
"""
import argparse
import subprocess
import sys
from pathlib import Path

DATASETS = {
    "numbers.json": "numbers", "runs.json": "runs", "ratings.json": "ratings", "tasks.json": "tasks",
    "waiting.json": "waiting", "egress.json": "egress", "latency.json": "latency",
    "seats.json": "seats", "shipped.json": "shipped",
}
AREAS = {"feat": "command", "fix": "data", "docs": "docs", "test": "safety", "ci": "docs", "chore": "docs", "release": "docs"}


def shipped_rows(listing):
    """Rows {pr, area, what} from `gh pr list --state merged --json number,title` output, oldest first."""
    rows = []
    for pr in sorted(listing, key=lambda p: p.get("number", 0)):
        title = str(pr.get("title") or "").strip()
        head, _, rest = title.partition(":")
        area = AREAS.get(head.strip().lower(), "docs") if rest else "docs"
        rows.append({"pr": int(pr["number"]), "area": area, "what": (rest or title).strip()[:140]})
    return rows


def write_extra(out, run=subprocess.run):
    """seats.json (from lifeos/seats.py) and, when `gh` works, shipped.json (from the merged pull requests)."""
    import json
    from lifeos import seats
    out = Path(out)
    (out / "seats.json").write_text(json.dumps(seats.capability_rows(), ensure_ascii=False, indent=1), encoding="utf-8")
    written = [out / "seats.json"]
    try:
        done = run(["gh", "pr", "list", "--state", "merged", "--limit", "60", "--json", "number,title"],
                   capture_output=True, text=True, timeout=60, cwd=Path(__file__).resolve().parents[1])
        if done.returncode == 0:
            (out / "shipped.json").write_text(json.dumps(shipped_rows(json.loads(done.stdout)), ensure_ascii=False, indent=1), encoding="utf-8")
            written.append(out / "shipped.json")
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return written


def steps(written):
    """The hand-over text: which file feeds which dataset of the cockpit."""
    lines = ["Hand these files to Claude and ask: \"refresh the cockpit data\"", ""]
    for path in written:
        lines.append(f"  {Path(path).name:<14} -> dataset '{DATASETS.get(Path(path).name, '?')}'")
    lines += ["", "These files are private: load them only into a page only you can open."]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", help="folder for the files (default: lifeos-cockpit-export next to your home folder)")
    ap.add_argument("--home", help="the LifeOS home folder (default: as `lifeos` finds it)")
    args = ap.parse_args(argv)
    from lifeos.home import find_home
    from lifeos import dashdata
    from lifeos.cli import build_parser
    import argparse as _ap
    home = find_home(args.home)
    out = Path(args.out) if args.out else home.parent / "lifeos-cockpit-export"
    here = Path(__file__).resolve().parents[1]
    if here in out.resolve().parents or out.resolve() == here:
        print("refuse: the export folder must be outside this repo (the files are private)", file=sys.stderr)
        return 2
    commands = len(next(a for a in build_parser()._actions if isinstance(a, _ap._SubParsersAction)).choices)
    written = dashdata.export(home, out, commands=commands) + write_extra(out)
    print(steps(written))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(main())
