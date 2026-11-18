"""Scan the whole git history for class C data, not just today's files.

A secret that was committed once and deleted later is still public if the repo is public. This walks every commit on
every branch, checks only the lines each commit added, and reports commit, file and a masked excerpt (never the value).
"""
import subprocess

from . import guard


def scan(repo=".", max_commits=None):
    cmd = ["git", "log", "--all", "-p", "--no-color", "--no-ext-diff", "-U0", "--format=commit %H"]
    if max_commits:
        cmd.append(f"-{int(max_commits)}")
    proc = subprocess.run(cmd, cwd=repo, capture_output=True, check=True)
    private = guard.private_patterns()
    commits, findings, sha, name, added = 0, [], "", "", []

    def flush():
        if sha and name and added:
            for _line, sev, kind, excerpt in guard.scan_text("\n".join(added), private):
                if sev == "BLOCK":
                    findings.append({"commit": sha[:12], "file": name, "kind": kind, "excerpt": excerpt})

    for raw in proc.stdout.decode("utf-8", "replace").splitlines():
        if raw.startswith("commit ") and len(raw) == 47:
            flush()
            commits, sha, name, added = commits + 1, raw[7:], "", []
        elif raw.startswith("+++ "):
            flush()
            name, added = raw[4:].removeprefix("b/"), []
        elif raw.startswith("+") and not raw.startswith("+++"):
            added.append(raw[1:])
    flush()
    return {"commits": commits, "findings": findings}
