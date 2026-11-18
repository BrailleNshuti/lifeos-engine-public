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
