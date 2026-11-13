# State of lifeos-engine · 2026-11-13

Read this first (AGENTS.md rule for build repos). Keep it short and update it after meaningful merges.

## Now

- Version 0.1.0 on main. Commands: task, week, context (with `--explain`), ask, delegate, review, sort-csv, mcp, guard, doctor (with `--tools`).
- PR #18 enforces the 2,000-token always-loaded core cap; the data repo was trimmed below it.
- PR #22 hardened the privacy and persistence boundaries: remote Ollama is refused centrally, untrusted text cannot self-allow, assigned secrets block, `store.py` owns result/ledger writes, the ask/week contract is shared, context budgets are bounded, and cross-module private API uses are zero.
- Execution Kernel Lite added: atomic sibling-temp-and-replace writes and duplicate-retry idempotency in `store.py`, immutable JSONL run records (`logs/runs.jsonl` with `run_id`, `parent_run_id`, `context_sha256`, `duration_ms`), `lifeos context --explain`, `lifeos doctor --tools`, and `lifeos review` (Rule 7 blind multi-model review stripping prior `## Result` blocks). 167 tests pass.
- The private data repo now has its own dependency-free privacy/core-budget workflow (lifeos PR #23).
- Code routing decision D23 remains: Claude writes, Codex checks.
- Public from v0.3: no personal data; examples are fabricated.

## Open

- PR #21 merged the Prompt Lab design document only; implementation remains gated on two weekly cycles of real-use evidence.
- Six historical Actions runs from 11 Nov remain queued with zero jobs; current CI is healthy. Ignore or delete them in the Actions UI.
- Before a public release, set the GitHub commit email to a private address. Rewrite history only if the owner explicitly chooses it.
- External CLIs still require periodic live smoke tests; an empty working directory is not an OS sandbox.

## Next

- Freeze feature work for two weekly cycles.
- Use the current core on at least 20 real tasks, 10 real model calls and two weekly reviews.
- Record corrections, elapsed time, failed calls and evidence. Decide the next feature from those numbers.
