# State of lifeos-engine · 2026-11-13

Read this first (AGENTS.md rule for build repos). Keep it short and update it after meaningful merges.

## Now

- Version 0.1.0 on main. Commands: task, week, context (with `--explain`), ask, delegate, review, sort-csv, mcp, guard, doctor (`--tools`, `--live`, `--smoke`), lab (`check`, `pack`, `score`).
- PR #18 enforces the 2,000-token always-loaded core cap; the data repo stays below it.
- PR #22 hardened the privacy and persistence boundaries: remote Ollama is refused centrally, untrusted text cannot self-allow, assigned secrets block, `store.py` owns result/ledger/proof/run writes, the ask/week contract is shared, context budgets are bounded, and cross-module private API uses are zero.
- Execution Kernel (PRs #26, #28-#32): pre-execution `run_id` generation and retry idempotency (`--run-id`), locked crash-recoverable multi-file commits (`logs/.store.lock` with live-PID verification + token-checked release, `os.fsync` atomic replacement, `logs/.store.journal.json` with `home` allowlist and corrupt-journal quarantine), schema-versioned (`schema_version: 2`, UTC `started_at`/`finished_at`, `terminal: true`) run records in `logs/runs.jsonl` with v1 compatibility normalization, recording of blocked/failed/timeout/tool-missing/partial runs with secret redaction, parent `review_group` records, `lifeos doctor --tools [--live|--smoke]` probes (`healthy` for local Ollama model checks, `cli_healthy` for CLI `--version`, `healthy` for authenticated `--smoke`), and `lifeos review --repo <path> --commit <sha>` with per-reviewer isolated detached `git worktree` + commit diff inspection.
- Prompt Lab offline runner (PR #27, `lifeos/labcard.py`, `lifeos/labscore.py`, `lifeos/lab.py`, `lifeos lab {check,pack,score}`) built per `docs/PROMPT-LAB.md` with strict no-model/no-network layering enforcement and store-locked deduplicated proof logging in `logs/proofs.csv`.
- The private data repo has its own dependency-free privacy/core-budget workflow (lifeos PR #23).
- Code routing decision D23 remains: Claude writes, Codex checks.
- Public from v0.3: no personal data; examples are fabricated.

## Open

- Six historical Actions runs from 11 Nov remain queued with zero jobs; current CI is healthy. Ignore or delete them in the Actions UI.
- Before a public release, set the GitHub commit email to a private address. Rewrite history only if the owner explicitly chooses it.
- External CLIs still require periodic `--smoke` tests; an empty working directory is not an OS sandbox.

## Next

- Freeze feature work for two weekly cycles.
- Use the current core on at least 20 real tasks, 10 real model calls, actual Prompt Lab runs, and two weekly reviews.
- Record corrections, elapsed time, failed calls and evidence. Decide the next feature from those numbers.
