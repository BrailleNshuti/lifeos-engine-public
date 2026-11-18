# Changelog

Dates are release dates. Newest first.

## [Unreleased]

- `lifeos ask`, `delegate` and the MCP tools attach notes listed under `## Context` of a task (max four `.md`/`.txt` files inside the data repository, trimmed to a token cap, guarded like the rest of the pack). Models no longer need a pasted copy.
- Privacy guard: now also blocks lowercase IBANs, IBANs written with dashes or dots, dotted card numbers, and a card number that ends a sentence. Found by new property tests that generate many checksum-valid identifiers in many layouts.
- `lifeos verify`: new run records carry the hash of the previous line (tamper-evident ledger); `--anchor` catches a rewritten last record or a cut tail.
- `lifeos replay <run-id>`: proves an `ask` run's input is unchanged, or names the file that changed. Run records now keep per-file digests and the task length (no content).
- `lifeos canary`: reproducible guard score on generated fake identifiers, and an end-to-end proof that `ask` refuses to send them.
- Budget governor: `lifeos ask` checks the weekly cloud budget, the seat's share and usage-limit rests before sending and holds the call (exit 4) unless `--force`. Tokens and calls, not euros: the engine uses subscription tools and has no prices.
- `lifeos panel`: ask two to four models the same task blind (identical pack, no cross-leak) and get a report of agreements, conflicts and single-model claims appended to the task. Same-input proof via the pack hash; each run is a normal ledger record and replayable.
- `lifeos rate`, `lifeos learn`, `delegate --learned`: rate a model's work per kind of task; the router follows the ratings only with enough evidence (3+ ratings and a full-point gap), otherwise the default stands.
- `lifeos predict`, `resolve`, `calibration`: decision calibration with an append-only log, a Brier score and confidence bands; says "too few results" until five predictions are resolved.
- `lifeos mistakes`: a quiz from the verified questions you miss most. `lifeos vocab`: your own German words with a simple review schedule, kept local.
- `lifeos numbers`: an "Engine in numbers" page built from the code, the guard score and the ledger (counts only).
- `lifeos prove`, `history-scan`, `hook install`, `digest`: one proof file, a whole-history secret scan, a pre-commit guard hook and a Sunday review in numbers.
- `lifeos demo`: a 60-second tour of the engine's promises on made-up data. `lifeos savings`: measured token savings from your ledger. `lifeos numbers --html`: one self-contained page (no script, no links).
- README "See it in 60 seconds" section, `docs/DESIGN.md` (each design decision and what it costs) and a `proof` workflow that runs the demo, `prove`, `numbers` and `history-scan` on every pull request and attaches `proof.md` and `numbers.html` as an artifact (made-up demo home only).
- `lifeos completion powershell|bash`: tab-completion generated from the real parser.
- `lifeos timeline`: proofs and minutes saved per week with a bar. Read-only.
- `lifeos schema` and `docs/LOGS.md`: the format of every file the engine writes, generated from the code and pinned by a drift test.
- `lifeos stale`: open tasks, unresolved predictions and due decisions older than N days. Read-only.
- `lifeos lint`: task-file checks (front matter, done_when, level, status, due, proof on done tasks). Read-only.
- `lifeos today`: one-screen daily view (next task, due decisions and words, open predictions, running experiment). Read-only.
- Tests: docs drift (every command has a README row), `--help` for every command, and parallel writers (8 threads, 5 processes) that must keep the ledger chain valid. README rows added for `bakeoff`, `exam`, `showcase`.
- `lifeos earn`: uses per part in the last N days, from the logs each part writes (rule 10). Removes nothing.
- `lifeos release`: read-only release plan (version check, proposed bump, draft notes). Never tags.
- Budgets as tests: CLI import time, everyday command speed, a size ratchet per module, and a standard-library-only check.
- Robustness: seeded garbage in every log (short rows, extra columns, bad bytes, NUL, huge lines) no longer crashes any read command. New `store.read_csv_rows` is the one tolerant reader; `runs` no longer fails on null fields.
- `lifeos redact`: guard-driven copies for sharing; flagged lines replaced, result re-scans clean.
- `lifeos backup`: hashed copy of `logs/` and `--check` to verify it; never overwrites, never inside the home.
- `lifeos decide`: decision records (`add`, `list`, `due`) with a revisit date and an optional linked prediction.
- `lifeos pipeline`: saved multi-step flows with stop/continue gates; dry run unless `--run`; no nesting.
- `lifeos experiment`: one tested rule change at a time (start, end, list). Kept only if the chosen metric improves by 5 % or more over the trial; too little data is inconclusive, never a silent keep.
- `lifeos selftest`: 24 commands run on a throwaway copy of the demo home, PASS or FAIL each. Never touches your notes.
- `lifeos arch` and `docs/ARCHITECTURE-GRAPH.md`: the module graph drawn from the real imports, with a test that fails when the checked-in graph is stale. After adding a module, run `lifeos arch --write docs/ARCHITECTURE-GRAPH.md`.
- Ledger attack tests: 70 seeded random attacks (edit, delete, swap, forge, duplicate, tear) are all caught by `verify`; cutting the tail and rewriting the last record are caught only with the saved head hash, as documented.
- `savings` and the numbers page now lead with the measured tokens per cloud run and show the comparison with pasting every note as a ceiling (a worst-case baseline), not as a typical saving.
- `history-scan` reads `.lifeos-history-allow` for reviewed exceptions (exact commit and file, with a reason). The first one is a made-up key in an early draft of `demo.py`.
- A damaged line in `logs/runs.jsonl` no longer crashes every reader; `lifeos verify` still reports it. Found by new chaos tests (torn line, CRLF checkout, CSV without final newline, garbage rows).
- `lifeos numbers` now says "Test functions" (parametrized tests run more checks than there are functions).

## [0.3.0] - 2026-11-18
First public release.

### Added
- Prompt Lab runner: `lifeos lab check/pack/score` (prompt cards validated, packed, scored offline with proof logging).
- Seats with failover chains and one cloud budget; rest-until logic that reads absolute and relative reset times (for example "resets in 2h 30m").
- `lifeos doctor --smoke [--only a,b]`: probes seats, prints why a probe failed, records a rest for seats that hit a usage limit, skips resting seats.
- LICENSE (MIT), SECURITY.md, CONTRIBUTING.md, docs/RELEASE-CHECKLIST.md.

### Changed
- Grok seat uses its real command-line flags.
- Work-related wording removed from code, skills and examples; a test keeps it out.
- Version bumped from 0.1.0.

## [0.1.0]
Task files, weekly numbers, context packs, privacy guard, doctor, five skills, CI.
