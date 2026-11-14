# State of lifeos-engine · 2026-11-14

Read this first (AGENTS.md rule for build repos). Keep it short and update it after meaningful merges.

## Now

- Version 0.1.0 on main. Commands: task, week, log (`proof`, `ledger`, `health`, `hours`), runs, context (with `--explain`), ask, delegate, review, sort-csv, mcp, guard, doctor (`--tools`, `--live`, `--smoke`), lab (`check`, `pack`, `score`).
- PR #18 enforces the 2,000-token always-loaded core cap; the data repo stays below it.
- PR #22 hardened the privacy and persistence boundaries: remote Ollama is refused centrally, untrusted text cannot self-allow, assigned secrets block, `store.py` owns result/ledger/proof/run writes, the ask/week contract is shared, context budgets are bounded, and cross-module private API uses are zero.
- Execution Kernel (PRs #26, #28-#42, #49-#53): pre-execution `run_id` generation and retry idempotency (`--run-id` on CLI and `run_id` on MCP `lifeos_ask`/`lifeos_review`), per-run advisory locking (`logs/.run.<id>.lock`) + locked crash-recoverable multi-file commits (`logs/.store.lock` on persistent inode, `os.fsync` atomic replacement, `logs/.store.journal.json` with `home` allowlist and corrupt-journal quarantine), schema-versioned (`schema_version: 2`, UTC `started_at`/`finished_at`, `terminal: true`) run records in `logs/runs.jsonl` with v1 compatibility normalization, recording of blocked/failed/timeout/tool-missing/partial runs with secret redaction on both persisted records and propagated CLI/MCP errors, parent `review_group` records, `lifeos doctor --tools [--live|--smoke]` probes, `lifeos review --repo <path> --commit <sha>` with sanitized repository basenames, read-only restricted Claude review invocations, and stdin `stream-json` Gemini (`agy`) execution in an isolated temp directory.
- Logging, analytics, and data policy (PRs #54-#55): `lifeos log {proof,ledger,health,hours}` with UTF-8/LF/range/duplicate/guard validation, `lifeos week` summaries for `hours.csv` and `health.csv`, `lifeos runs` execution audit inspector, and 5-tier data classification policy (`PUBLIC`, `INTERNAL`, `PERSONAL`, `SENSITIVE`, `SECRET`) in `lifeos/policy.py`.
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
