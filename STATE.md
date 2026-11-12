# State of lifeos-engine · 2026-11-12 (night)

Read this first (AGENTS.md rule for build repos). Short, dated, updated at each merge.

## Now
- Version 0.1.0 on main (2945d24). Commands: task, week, context, ask, delegate, sort-csv, mcp, guard, doctor.
- PRs 1 to 15 are all merged, including hardening 2 and 3: private delegate stays local (owner decision D22, 12 Nov: a private task stops if Ollama is down), guard --staged reads the staged file and counts renames and skipped files, MCP task_new is guarded, BOM/UTF-16/bad-regex handling, proxy bypass for local Ollama, timeout error, sort-csv fixes, MCP input checks.
- Checked 12 Nov on the laptop: `python -m pytest -q` 144 passed.
- Code routing (D23): Claude writes, Codex checks.
- Goes public from v0.3: no personal data, ever; examples/ made up. No release date is set (D20).

## Open
- Six old CI runs from 11 Nov show "queued"; GitHub refused to cancel them (409). Delete them in the Actions tab or ignore them.
- Branch protection is on (owner, 12 Nov).
- Before v0.3: the git history holds the owner's real name and personal email on 15 commits. Decide: GitHub private email for new commits (recommended), history rewrite only if wanted.
- Public-readiness scan verdict (Day 1 routine) lives in that run's session, not in this repo.

## Next
- Prompt Lab runner (v0.3 feature) once the owner starts it.
- `lifeos doctor` core files measured about 2042 tokens on 12 Nov, over the 2,000 cap in plan; trim or change the cap.
