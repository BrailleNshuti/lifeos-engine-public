# State of lifeos-engine · 2026-11-12

Read this first (AGENTS.md rule for build repos). Short, dated, updated at each merge.

## Now
- Version 0.1.0 on main. Commands: task, week, context, ask, delegate, sort-csv, mcp, guard, doctor.
- Merged 11 to 12 Nov: ask, mcp, delegate (qwen), free answer check, sort-csv, scoreboard (`Delegation:` line in `lifeos week`), sort-csv flags "other", hardening 1, README sync (PRs 1 to 11).
- Checked 12 Nov on the laptop: `pytest -q` 125 passed, `lifeos guard` ok on 44 files.
- Goes public from v0.3: no personal data, ever; examples/ made up. Public scan (Day 1 routine, 12 Nov): verdict is in that run's session, not in this repo.

## Open
- PR 12: hardening 2, four privacy holes (private delegate stays local, guard --staged reads the staged file, guard counts skipped files, MCP task_new guarded). Not merged.
- Hardening 2 candidates still open: proxy leak; guard misses renamed files; ledger injection via `lifeos_result_write`; MCP crash on non-object JSON; private-patterns BOM, UTF-16 and bad regex; sort-csv sniffer, short rows and first-row echo; Ollama read timeout reported as "tool missing"; quadratic email regex; delegate docstring says code -> Codex while ROUTES send code to claude; `week --week 2026-47` error message.
- Four old CI runs from 11 Nov (25 to 28) still show "queued": cancel in the Actions tab.
- Main is not protected (branch protection is the owner's GitHub setting).

## Next
- Owner merges PR 12 and runs `python -m pytest -q` (expect 129).
- v0.3 date is open (D15: proposed 20 Dec). Fix the private-path holes before it goes public.
