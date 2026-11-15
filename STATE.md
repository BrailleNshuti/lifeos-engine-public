# State of lifeos-engine · 2026-11-15

Read this first (AGENTS.md rule for build repos). Keep it short and update it after meaningful merges.

## Now

- Version 0.1.0 on main. Commands: task, week (`--draft`, `--redteam`), log (`proof`, `ledger`, `health`, `hours`), runs, kaizen (`--draft`), route, cockpit (`--export`, `--serve`), study (`sources`, `import`, `bank`, `verify`, `attempt`, `exam`, `curricula`, `refresh`, `gaps`), context (with `--explain`), ask, delegate, review, sort-csv, mcp (16 tools), guard, doctor (`--tools`, `--live`, `--smoke`), lab (`check`, `pack`, `score`), exam, bakeoff and showcase.
- PR #18 enforces the 2,000-token always-loaded core cap; the data repo stays below it.
- PR #22 hardened the privacy and persistence boundaries: remote Ollama is refused centrally, untrusted text cannot self-allow, assigned secrets block, `store.py` owns result/ledger/proof/run writes, the ask/week contract is shared, context budgets are bounded, and cross-module private API uses are zero.
- Execution Kernel (PRs #26, #28-#42, #49-#53): pre-execution `run_id` generation and retry idempotency (`--run-id` on CLI and `run_id` on MCP `lifeos_ask`/`lifeos_review`), per-run advisory locking (`logs/.run.<id>.lock`) + locked crash-recoverable multi-file commits (`logs/.store.lock` on persistent inode, `os.fsync` atomic replacement, `logs/.store.journal.json` with `home` allowlist and corrupt-journal quarantine), schema-versioned (`schema_version: 2`, UTC `started_at`/`finished_at`, `terminal: true`) run records in `logs/runs.jsonl` with v1 compatibility normalization, recording of blocked/failed/timeout/tool-missing/partial runs with secret redaction on both persisted records and propagated CLI/MCP errors, parent `review_group` records, `lifeos doctor --tools [--live|--smoke]` probes, `lifeos review --repo <path> --commit <sha>` with sanitized repository basenames, read-only restricted Claude review invocations, and stdin `stream-json` Gemini (`agy`) execution in an isolated temp directory.
- Logging, analytics, and data policy (PRs #54-#55): `lifeos log {proof,ledger,health,hours}` with UTF-8/LF/range/duplicate/guard validation, `lifeos week` summaries for `hours.csv` and `health.csv`, `lifeos runs` execution audit inspector, and 5-tier data classification policy (`PUBLIC`, `INTERNAL`, `PERSONAL`, `SENSITIVE`, `SECRET`) in `lifeos/policy.py`.
- Study Atelier v2 (PR #63): Cockpit defaults to Study Desk/Source Library/Recall Studio/Exam Forge/Mastery with day/night and focus modes, recovery mode and proof shelf. The dependency-free study core imports privacy-guarded Markdown/text notes, generates deterministic source-excerpt questions, requires human verification, schedules retrieval attempts and writes frozen exam papers plus separate keys. Static exports redact every answer; live answer/review endpoints require the per-process nonce, localhost, JSON and size checks.
- Adaptive Learning v1 (active branches `codex/adaptive-learning-v1` and `codex/adaptive-learning-data-v1`): seven ordered learning journeys cover all 19 reset skill areas. The Cockpit now shows previous/current/next lessons, progress, streaks, a gap clinic and interactive quick tests. Committed answers are rubric-scored from explicit source key points; attempts update scheduling and curriculum progress while raw responses and missing-concept text stay out of static exports. Question-bank refresh is deterministic and never auto-promotes unreviewed material.
- Local model kit (active branch): one Ollama runtime with three laptop-sized roles—Qwen 3.5 4B tutor, DeepSeek-R1 1.5B reasoner and Qwen 2.5 Coder 3B—plus PowerShell install/use scripts and a data-repo registry. Installation still needs to be run from a normal PowerShell session because this build sandbox cannot access `winget`.
- Cockpit Design v3 + Communication Hub (active branch): replaced the low-contrast palette with explicit WCAG-AA day/night foreground aliases and browser-verified desktop/mobile layouts. The new draft-first hub reads only a credential-free channel manifest, stores optional drafts in browser local storage, and models Gmail, Outlook and official WhatsApp Business as read-on-request -> summarize -> draft -> explicit-send-confirmation; credentials and message bodies never enter the static export or repository.
- Project Building Chamber: the Cockpit loads a versioned market-backed roadmap from the data repo, renders track/stage filters, exact build procedures and proof gates, and includes a browser-local recruiter interview simulator. The initial private roadmap covers 19 cumulative AI, Data and ML builds; mastery remains evidence-based and starts from a user-requested zero baseline.
- Prompt Lab offline runner (PR #27, `lifeos/labcard.py`, `lifeos/labscore.py`, `lifeos/lab.py`, `lifeos lab {check,pack,score}`) built per `docs/PROMPT-LAB.md` with strict no-model/no-network layering enforcement and store-locked deduplicated proof logging in `logs/proofs.csv`.
- The private data repo has its own dependency-free privacy/core-budget workflow (lifeos PR #23).
- Code routing decision D23 remains: Claude writes, Codex checks.
- Public from v0.3: no personal data; examples are fabricated.

## Open

- Six historical Actions runs from 11 Nov remain queued with zero jobs; current CI is healthy. Ignore or delete them in the Actions UI.
- Before a public release, set the GitHub commit email to a private address. Rewrite history only if the owner explicitly chooses it.
- External CLIs still require periodic `--smoke` tests; an empty working directory is not an OS sandbox.
- Gmail, Outlook, WhatsApp Business and phone notifications are not autonomous senders. The current boundary is local nudge + draft-first communication; every external send still needs explicit owner approval. Background reminders require an OS scheduler or a hosted service and are deliberately outside the static Cockpit.

## Next

- Open pull requests for the two adaptive-learning branches, review CI, and let the owner merge them; do not bypass the repository's PR-only automation rule.
- From a normal PowerShell, run `scripts/install-local-models.ps1 -InstallRuntime`, then `lifeos doctor --tools --smoke` and record model latency before keeping or pruning models.
- Test the adaptive loop tomorrow with real answers: complete one journey step, one 10-question quick test and one gap-clinic retry; fix only observed friction during the feature freeze.
- Finish the user-authorized Gmail/Outlook OAuth choice and official WhatsApp Business eligibility check only when an actual communication workflow is chosen.
- Use the current core on at least 20 real tasks, 10 real model calls, actual Prompt Lab runs, and two weekly reviews.
- Record corrections, elapsed time, failed calls and evidence. Decide the next feature from those numbers.
