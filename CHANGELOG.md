# Changelog

Dates are release dates. Newest first.

## [Unreleased]

- Tests: the `lifeos ask` CLI path now has an end-to-end fake-adapter check for its seat hint, free CHECK line and successful exit code.
- Tests: direct coverage for the pre-call seat hint and post-call answer check, including missing task files that must never raise.
- Docs: `docs/HANDOFF.md`, the document for the next model to continue the build: rules, workflow, traps, a test and feature backlog with a done-when for each, and how to log progress. `AGENTS.md` points to it.
- New: the privacy guard now also blocks a JSON web token, a US-style social security number (nnn-nn-nnnn), a tax or social security number after its label (Steuer-ID, tax id, ...) and a stated PIN ("PIN is nnnn"). Found by probing with made-up values; nothing blocked a bare number, so ordinary digits, dates, ISBNs and version strings are unchanged (19 new cases in `tests/test_guard_more.py`, 9 of them harmless look-alikes).
- New: a table of what each seat has no tool for (`seats.CANNOT`), shown as a hint before `lifeos ask` and never as a block: Grok cannot read shop sites, change files or run commands; the local models have no web access. Tests first in `tests/test_seat_hints.py`.
- Docs: `docs/DAILY.md`, one page for daily use: the five-step loop, which seat for which job, and what each failure seen in week one means.
- New: `lifeos dash-export --out DIR` writes the five JSON files a dashboard needs (numbers, runs by seat, ratings with notes, tasks, and an optional hand-kept `waiting.json`). No model call. The files are private. Tests first in `tests/test_dashdata.py`.
- Refactor: eleven command helpers moved from `lifeos/cli.py` to `lifeos/cmds_misc.py` (study, lab, doctor, vocab, guard, sort-csv and what they call), so `cli.py` drops from 1,241 to about 1,000 lines and has room for new commands. Same code, same behaviour; full suite 858 passed.
- Test: `tests/test_readme_matches_code.py` fails if the README names a command that does not exist, and if any command lacks a help line (58 checks, all passing today).
- New (from the first week of real use, tests first in `tests/test_seat_hints.py`): a `kind:` line in a task file now decides the rating's kind, so long pasted context can no longer file a rating under the wrong kind; `lifeos rate` says so when the route names a review step and no review result is in the task; `lifeos ask grok` prints a hint (never a block) when the task asks for shop prices, because shop and price-comparison sites block the seat's `web_fetch`; and a local model call now gives up after 240 s instead of 600 s (`LIFEOS_TIMEOUT` still overrides) so another seat can take over. Cause: Qwen 4B on this CPU did not answer in 600 s twice.
- New: the free answer check (`lifeos/check.py`, no model call) now also reads the task. It flags a `done_when` that asks for a URL or a date when the answer has none, a seat that only promises to save its result (it has no write tool), and quoted lines that are not in the task context (only when the context holds at least 1500 characters, because a seat that fetches its own pages quotes text we never gave it). `lifeos ask` now prints the same `CHECK` line `delegate` already did, and both record the flag count. Replayed on this week's real answers: the narration-only Grok answer is flagged, the good ones are not. Tests first in `tests/test_check_done_when.py`.
- Fix: `atomic_write_bytes` (found in a Codex review, checked against the code, test first in `tests/test_atomic_write_edges.py`): a rewrite keeps the permission bits of the file it replaces (a 0600 file no longer becomes 0644 on POSIX), and removing the temp file in `finally` is best effort, so a scanner holding it can no longer replace the real error with a cleanup error. The review's third finding (diagnostics can raise) was wrong: `diag.report` and `diag.recovered` catch everything.
- Fix: the Grok seat now gets one fixed rule in front of every prompt (`GROK_RULE`): put the whole answer in the reply, you cannot save or write anything. In real use on 2026-11-26 two of two answers were only "I'll save the result" with no content, because the seat has no write tool. After the fix one real question (a German registration deadline and fine, two public law pages) came back with the figures, quotes, URLs and date, matching a manual reading (n=1). Also found: price-comparison sites block the seat's `web_fetch`, so it cannot answer shop-price questions. Test first in `tests/test_grok.py`.
- Fix: the Grok seat is now locked for real. A live check showed that `--permission-mode dontAsk` alone let a read-only shell command run and refused `web_fetch`, so the seat could not answer live-facts questions. `ask_grok` now passes `--tools web_fetch --allow web_fetch`: shell and file probes get no tool, a live fact is answered with its source. Test first in `tests/test_grok.py`; the probes and what is not shown are in `docs/LIVE-CHECK.md`.
- Fix: the card-number check no longer fires on a run id such as `R-261116-60279634` (an all-digit suffix can pass the checksum by chance). `history-scan` has a reviewed exception for the made-up key in the first draft of `lifeos/demo.py`, so the `proof` check is green again.
- Fix: the roadmap table and a guard test no longer name private milestones; the dates stay. The hygiene test now rejects any numbered private-milestone label.
- `scripts/soak.py` (standard library): runs the full suite N times with `LIFEOS_REPLACE_DIAG` set and prints, per run and in total, the exit code and the `os.replace` recovered and failed counts. Three runs on Windows: 829 passed each, recovered 0, failed 0, so the retry was still not exercised.
- Docs: `docs/DEBATE.md` has a "Seats concede" section: the evidence gate checks that a pointer exists, not that it is true, and one trial (n=1, made-up question, not adopted) with a stricter round 3 prompt (rebut only with a command the seat ran) still gave zero OPEN verdicts; one of its three seats timed out in round 3 and the Claude seat has no shell.

## [0.5.0] - 2026-11-20

- Fix: no personal data in the public tree. The cockpit no longer hardcodes a study provider, a language exam, certification dates, a private milestone or a side project: it reads an optional `cockpit.json` from the data home (`owner`, `focus`, `horizon`, `targets`, `areas`; a missing or broken file means neutral defaults; `examples/demo-home/cockpit.json` is made up). The exam generator and `lifeos exam --module` default to "Core module". The skill that named a private side project is now `demo-readiness-check` with made-up content. `tests/test_public_hygiene.py` fails if a short list of those terms returns in any tracked file. The old values still exist in git history; see the pull request.
- `lifeos debate score --reveal` adds a per-seat scorecard (new module `lifeos/debatestats.py`, pure counting): how its own claims ended up (fell, open, held after a revision, unchallenged), the objections it raised and how many counted and landed, and what it did when objected to (conceded, left unanswered, rebutted, revised). A seat with no round 1 answer is shown as not having taken part, not as a row of zeros. Never shown without `--reveal`, and never in the JSON without it. It is evidence for choosing seats, not a ranking.
- Fix: a model's answer is no longer lost when its temporary working folder cannot be deleted. On Windows a helper process of a model CLI can hold a file in that folder for a moment after the CLI has answered, and cleaning it up raised `WinError 32` after the answer had been received (seen live: a debate seat failed this way). The cleanup error is now ignored; at worst an empty folder stays in the temp directory. Applies to every command that calls a model CLI (`ask`, `delegate`, `panel`, `review`, `debate`).
- `lifeos selftest` now runs 44 steps: a debate round trip with no model (start, two recorded answers, the next prompts, a score, a dry run, then the ledger chain) on the throwaway home. If the debate cannot start, its seven steps are reported as failures instead of vanishing. A test pins the README's step count to the code.
- `lifeos earn` has a row for `debate`: a use is a recorded answer (round 1 to 3); a start, a skipped seat and a failed call are not. The "ask / delegate / panel" row no longer counts debate records.
- Docs and help: references to a private plan (section numbers such as 10.3, appendix and decision ids, the phrase "work-lane") are removed from README rows, CLI help, MCP tool descriptions, docstrings, skills and two generated headings (`# Skills`, `# BUILD IN PUBLIC`). The router now says "confidential-work-data check". `tests/test_public_hygiene.py` fails if one comes back. Found by Gemini's docs review and checked against the code.
- Fix: a command no longer crashes with `UnicodeEncodeError` after its work is done. On Windows a console or redirected file in cp1252 cannot show a character such as `≤` or an arrow, and `lifeos delegate` died while printing a model's answer (the answer was already saved). `main` now switches stdout and stderr to print `?` for such a character; the encoding and the exit code are unchanged, and a stream that cannot be switched is left alone. New module `lifeos/console.py`.
- Fix: `lifeos debate` scores one claim per point of an answer instead of one per sentence. A numbered item (or a bullet, or a paragraph) with its sub-bullets and evidence lines is one claim; prose with no structure is still split into sentences. Found in the first live run, where 5 numbered items had become 30 claims; the same three answers now give 6, 5 and 6. Table rows are clipped to 160 characters.
- Fix: a short Windows sharing violation no longer fails a write. `store.atomic_write_bytes` tries `os.replace` again up to five times (pauses of 0.02, 0.05, 0.1, 0.2 and 0.4 s, 0.77 s in all) when, and only when, Windows reports winerror 5 or 32; any other error, and a lock that lasts, raises the original error at once or after the last try. Measured before the fix: 2 of 3 full test runs failed on exactly this (a just-written file briefly held by another process). A write that recovers is logged to `LIFEOS_REPLACE_DIAG` when set; one that does not is reported with the holder and the number of attempts.
- Diagnostics: when `os.replace` fails with PermissionError (a sharing violation on Windows), `store.atomic_write_bytes` now reports it once, on failure only: errno and winerror, both paths, whether they exist, the thread count, and the processes that hold the files (Windows Restart Manager through `ctypes`), and whether this process is one of them. It goes to stderr and, when `LIFEOS_REPLACE_DIAG` names a file, to that file as JSON lines. It never retries and never hides the error. New module `lifeos/diag.py`.
- `lifeos debate` (`start`, `next`, `record`, `run`, `score`): blind debate of two to four seats in three rounds (answer, object, defend). Each seat sees the others only as seeded labels A/B/C with provider names and 64-character hashes scrubbed, and at most 3 objections per answer. An objection needs a target, a claim, `kind: evidence` and a checkable pointer, or it is an opinion and does not count. `score` is rule-based, no model: every claim is SURVIVED (unchallenged or revised with evidence), FELL (conceded or unanswered) or OPEN (evidence on both sides, with the settle test). Agreement is logged, never used (rule 6). `debate.json`, the round 1 pack and every answer are hashed into the chained ledger and `score` refuses a changed one or a broken chain. Debate calls count toward the seat budget; pasted answers do not. `run` is a dry run unless `--run`. Protocol: `docs/DEBATE.md`.
- Fix: `lifeos release` proposed a minor bump (0.5.0) for fix-only entries, because it read the substring "new" inside "New tests render ..." as a feature. Entries that start with Fix, Docs, Tests, Robustness, CI, Chore or Refactor are now patch-level; a feature is an entry that begins with a command name (without fix wording) or says "new command/flag/option/feature" in words. The version and the tag stay the owner's decision.

## [0.4.1] - 2026-11-19

- Fix: `lifeos --help` crashed with `ValueError: unsupported format character` because the `predict` help text held a bare `%`. New tests render the top-level help and every parser's help at every depth, so no help string can break the front door again. Per-command `--help` was never affected.
- Docs: the README command table is headed "What it does" (it said v0.1 over a v0.4 table); `STATE.md` brought up to date.

## [0.4.0] - 2026-11-18

- Tests: a made-up home shaped like the first real one (a level with a note, TODO placeholders, CRLF files, older unchained ledger records). The Sunday pipeline must fail only on the placeholders, pass once they are filled in, and `verify --seal` must pin the older records.
- `lifeos verify --seal`: once, pins the older unchained records (count plus one hash) in `logs/runs.seal.json`; `verify` then reports any later change, removal or reordering of them. Never overwrites a seal; prints the hash to keep outside the file.
- `lifeos pipeline --run` ends with one summary line (counts per status and the exit code), so a scheduler or a person sees the result at a glance.
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
- Tests: 16 look-alike lines (SHAs, UUIDs, timestamps) the guard must not flag; a CRLF and BOM checkout must give the same answers and the same ledger verification as a Linux one.
- `docs/SECURITY.md`: 13 promises, each linked to the test that proves it (a test checks the links), plus what is not promised.
- `lifeos pipeline`: steps now run with the home as working folder (so `guard now.md` scans the real file). New examples `sunday` and `before-push`, tested on a copy of the demo home; `docs/PIPELINES.md`.
- `lifeos export`: redacted evidence page (proofs, numbers, ledger head, calibration, rhythm).
- `lifeos timeline`: proofs and minutes saved per week with a bar. Read-only.
- `lifeos schema` and `docs/LOGS.md`: the format of every file the engine writes, generated from the code and pinned by a drift test.
- `lifeos stale`: open tasks, unresolved predictions and due decisions older than N days. Read-only.
- `lifeos lint`: a level followed by a note (`L2 (renames are L3)`) is accepted; found on the first run against a real home.
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
- `lifeos selftest`: 37 steps run on a throwaway copy of the demo home, PASS or FAIL each. Never touches your notes.
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
