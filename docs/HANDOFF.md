# Handoff: continue building the engine (written 2026-11-27, for any coding model, first for Codex)

The previous model ran out of usage. You take over now. The owner wants 8 to 9 hours of continuous, careful work, no idle gaps,
and every step saved to GitHub so the next model can see exactly where you stopped. Read this whole file before you touch anything.

**Newest first: section 14 at the end of this file is the latest hand-off (2026-11-28): what is done, what is open and what to do next. Read it before the rest.**

## 1. Rules that cannot be broken

1. **No attribution, ever.** Never add `Co-Authored-By`, `Claude-Session`, "Generated with" or any model name as author or
   trailer to a commit or pull request. The owner is the only contributor. CI (`no-attribution`) fails if one appears.
   Check `git config user.name` before the first commit; do not change it.
2. **Public repo: no personal data.** Nothing real: no names, addresses, IDs, bank data, keys, tokens, health or tenant data.
   Everything in `examples/` is made up. Build fake values at run time inside tests (see `tests/test_guard_more.py`), so the
   guard never trips on your own files. The side project of the owner is paused: do not touch it and do not name it here.
3. **Python 3.10+, standard library only.** No new dependency.
4. **Tests first.** Write the test, run it, see it fail, then change the code. For a fix, the test must fail before the fix.
5. **Never without the owner:** send, buy, pay, subscribe, post, delete data, share personal data, change account or
   security settings, force-push, rewrite history, change branch protection. If a task seems to need one of these, stop and
   write it in the log under "Needs the owner" (section 7).
6. **Report facts, not hopes.** If a test fails, say so with the output. If you did not run something, say that. Never write
   "should work". Rule 1 of the project: proof or it did not happen.

## 2. The owner's authority, as given for this handoff

The owner said: full access, merge your own pull requests, save every step to GitHub. That means you may:
- create branches, commit, push, open pull requests on `lifeos-engine-public`;
- merge **your own** pull request with `gh pr merge N --merge --admin --delete-branch` **only after all 12 CI checks are green**
  (`gh pr checks N` lists them: `proof`, `trailers` and the `test` jobs for py3.10, py3.11, py3.13 and windows, for both the push and the pull request);
- never push to `main` directly (the `protect-main` ruleset blocks it) and never force-push.

## 3. Where things are (verified 2026-11-27)

- Repo: `lifeos-engine-public`, branch `main`, tag `v0.5.0`. About 954 tests collected; the last full local runs gave 916 passed, 2 skipped.
- Read first, in this order: `AGENTS.md`, `STATE.md`, `docs/DAILY.md`, `docs/DESIGN.md`, `CHANGELOG.md` (section Unreleased).
- One module per command in `lifeos/`. Seats (models) and their failover are in `lifeos/seats.py`; calls in `lifeos/ask.py`;
  the free answer check in `lifeos/check.py`; the privacy guard in `lifeos/guard.py`; atomic writes in `lifeos/store.py`.
- The private notes repo (tasks, logs, ratings) is not part of this repo and you have no access to it. Do not look for it.

## 4. The workflow, step by step (use it for every unit of work)

1. `git checkout main && git pull`, then `git checkout -b <type>/<short-name>`.
2. Write the test. Run only that test file: `python -m pytest tests/test_x.py -q`. It must fail for the right reason.
3. Make the change. Keep functions short.
4. Run the **gate tests** before you push, every time (about 3 minutes):
   `python -m pytest tests/test_arch.py tests/test_layering.py tests/test_budgets.py tests/test_readme_matches_code.py tests/test_docs_drift.py tests/test_public_hygiene.py -q`
5. Run `lifeos guard $(git ls-files)`; it must print no BLOCK line.
6. Add one bullet under `## [Unreleased]` in `CHANGELOG.md`. If a command changed, update its row in `README.md`.
7. `git add -A && git commit -m "<type>: <what>"`, then `git push -u origin <branch>`, then `gh pr create --title ... --body ...`.
8. Wait until no check is pending: `gh pr checks N`. All 12 must say `pass`.
9. Merge (section 2), then `git checkout main && git pull`.
10. At least once an hour, add a short line to the log (section 7) through a small docs pull request.

Run the **full suite** (`python -m pytest -q -p no:cacheprovider`, about 6 minutes) after any refactor, and before a release-like
batch. Run it alone: do not edit files in the repo while it runs, because several tests read the source tree
(module list, architecture graph) and will fail for the wrong reason.

## 5. Traps found on the way (each one cost a CI round)

| Trap | What happens | What to do |
|---|---|---|
| Size ratchet (`tests/test_budgets.py`) | `cli.py` max 1250 lines, `ask.py` 1100, every other module 800 | Put new code in a new module; never raise a limit |
| Layer map (`tests/test_layering.py`) | A new module not in `LAYER` fails; a module importing an equal or higher layer fails | Add the module to `LAYER` with a layer above everything it imports |
| Architecture graph | `docs/ARCHITECTURE-GRAPH.md` goes stale on any import change | `lifeos arch --write docs/ARCHITECTURE-GRAPH.md`, commit it (takes about 2 minutes, it runs tests) |
| Import cycle | A lazy `import` inside a function still counts in the graph | Pass the value in instead of importing the higher module |
| CHANGELOG conflicts | Every pull request adds a line at the same place | After `git merge origin/main`, remove the conflict markers and run `grep -c "^<<<<<<<" CHANGELOG.md`; it must print 0 **before** you commit |
| Guard flags its own files | A comment that looks like a PIN or key is a BLOCK | Rephrase the comment; build fake values at run time |
| Hygiene test | Private plan terms and the side-project name must not appear in public files | Do not write them |
| Load-sensitive speed test | `test_importing_the_cli_stays_fast` took 1.68 s once while other work ran (limit 1.5 s) | Run alone; see backlog item T13 |
| Windows quoting | Escapes such as `\b` or `\\n` get mangled when you write code through a shell heredoc | Write files with your editor tool, not a heredoc; check regexes after writing |
| Line endings | Git prints "LF will be replaced by CRLF"; that is harmless | Ignore the warning; do not convert files |
| Memory pressure | A 5-minute test run was once killed for low memory | Never run two full suites at once; use CI as the gate for the rest |
| Merged-looking but not | `gh pr merge` can answer "merge already in progress" | Run `gh pr list --state open`; it should be empty |

## 6. The backlog, in priority order. Each item has a "done when" you can check.

### A. Tests (the owner asked for the remaining tests to be finished; the previous model could not find a list of exactly 16, so this is the verified list; write it all, then look for more)

| id | Test to write | Done when |
|---|---|---|
| T1 | `notes.pre_notes` and `notes.post_notes` directly: a Grok shop task gives a hint; a bad answer gives a CHECK line; a missing task file gives `[]`, never an exception | file `tests/test_notes.py`, 4+ cases, all pass |
| T2 | `lifeos ask` end to end with a fake adapter: the CHECK line is printed, the hint goes to stderr, the exit code is 0 | passes on Linux and Windows CI |
| T3 | `call_timeout("ollama")` is the value passed to the local HTTP call, and the error message names it | test with a patched `_open_local` |
| T4 | `learn.explicit_kind` and `clean_kind`: CRLF files, trailing spaces, commas, over-long labels, empty value | parametrised, 6+ cases |
| T5 | `check.task_check_inputs` on a file with CRLF line endings and on one with no `done_when` line | both return sane values |
| T6 | `check.QUOTE` with curly quotes, nested quotes, quotes shorter than 25 characters, and a context of exactly 1,499 and 1,500 characters | boundary cases pass |
| T7 | `store.atomic_write_bytes` keeps the mode on POSIX when the target is a symlink or read-only, and still works when the target does not exist (Linux CI only; skip on Windows with a reason) | passes on the Linux jobs |
| T8 | Every moved handler in `lifeos/cmds_misc.py` (study, lab, doctor, vocab, guard, sort-csv) has one smoke test through `main([...])` with a demo home | six tests, exit codes asserted |
| T9 | `dashdata.export` with a rating note holding commas, quotes, a newline and non-ASCII text; and with a missing `ratings.csv` | JSON stays valid, no exception |
| T10 | `dashdata` never writes a task body, only id, status, due and the first 90 characters of the goal | assert on the keys and the length |
| T11 | Documentation drift for all docs, not only the README: every `lifeos <command>` named in any `docs/*.md` exists | extend `tests/test_readme_matches_code.py` |
| T12 | Guard property test: for 500 seeded random harmless sentences made of ordinary words, dates, versions and counts, `scan_text` has no BLOCK | deterministic seed |
| T13 | Make `test_importing_the_cli_stays_fast` robust: take the median of 3 runs, keep the 1.5 s limit | no flake under load; the comment "about 0.1 s today" is corrected to the measured 0.5 to 0.7 s |
| T14 | `seats.seat_warning` for every seat in `CANNOT`, plus a test that every key of `CANNOT` is a real seat | table and seats cannot drift apart |
| T15 | Failover in `delegate`: first seat times out, second answers; a SENSITIVE task never reaches a cloud seat even when every local seat fails | both outcomes asserted |
| T16 | A "docs state the truth" test: the test and module counts quoted in `docs/proof.md` and `STATE.md` are regenerated by `lifeos prove`/`lifeos numbers`, or the doc says it is a dated snapshot | no stale number without a date |

If you find tests that are missing beyond these, add them and list them in the log. Coverage by guess is not enough: for each
module in `lifeos/` that has no direct test file, write one meaningful test or note in the log why it is covered elsewhere.

### B. Features (each small, each its own pull request, each with tests first)

1. **Seat reroute, not only a hint.** If a task needs something its seat has no tool for (`seats.CANNOT`), `lifeos delegate` picks the next seat in the chain and says why in the route note. `ask` keeps printing a hint only. Done when a test shows the reroute and one shows that a private task still never leaves the laptop.
2. **Local model warm-up.** Before a local call, a tiny request loads the model, and the real call gets its own timeout. Done when the first call after idle uses the warm-up and a test with a fake server proves the order. Do not run it against the real model in tests.
3. **Latency in `lifeos earn`.** Per seat: median and worst seconds from the run ledger, and the failure count. Done when the numbers match a hand count on a demo ledger.
4. **`lifeos verify-quotes <task>`.** The quote check on its own, for answers already in a task file: prints real over total and the missing lines. No model call.
5. **A "no result recorded" guard.** If a seat answers but the task file gets no result (disk error), `ask` says so and exits non-zero. Done when a failing-write test shows it.
6. **`lifeos_debate` MCP tool** (idea in `STATE.md`): only if the existing MCP tests stay green and the tool never sends a private task to a cloud seat.
7. **Dashboard export extras:** `dash-export --check` prints what changed since the last export; no network.
8. **Nightly scheduled check:** a GitHub workflow that runs the suite three times on `windows-latest` and posts the `os.replace` recovered/failed counts in the job summary (to catch the Windows write flake in CI). Read `scripts/soak.py` first. Done when one scheduled or manual run shows the counts.

### C. Robustness (the owner wants a stronger system)

- Failure injection: for each seat adapter, a test where the CLI is missing, returns empty output, returns garbage, hangs past the timeout, and returns a usage-limit message. The error text must be short and redacted, and the ledger must record the failure once.
- Windows paths and encodings: console output with non-ASCII characters on cp1252 must not crash any command (see `lifeos/console.py`).
- Concurrency: two processes calling `append_run_record` and `atomic_write_bytes` on the same file never lose a line (the existing tests use threads; add a two-process test).
- The privacy guard: add shapes only when you can show a made-up example that slips through and a harmless look-alike that must stay clean (the pattern used in `tests/test_guard_more.py`). Never block a bare number.
- Every command that writes files must refuse to write outside the home folder given by `--home`. Test with a path containing `..`.

### D. Open question you cannot solve

The Windows `os.replace` write failure (winerror 5) has never reproduced locally: over 10 full runs and 8,000 direct writes the retry never fired. Do not "fix" it by guessing. Item B8 is the way to catch it. If it ever fails in CI, keep the log, and write the diagnostic output into `docs/LIVE-CHECK.md`.

## 7. How to work for 8 to 9 hours without losing the thread

- Work in a loop: pick the next item, do steps 1 to 9 of section 4, merge, pick the next. Do not wait for the owner between items.
- If a step fails twice in a row, stop that item, write what you tried and the exact error in the log, and move to the next item.
- Keep a log in `STATE.md`: add one short bullet under "Built" (a test fails when a bullet is longer than 400 characters). After every merged item or every hour, whichever comes first, add one factual line: time, pull request number, what changed, what failed, what is next. Push it through a docs pull request.
- If you are near your own usage limit, finish the current merge, write the log line, and add "Next up: <item>" so the next model can start at once. Never leave an unpushed branch, uncommitted files or a half-merged pull request.
- Heads-up for the end: before you stop, `git status` must be clean, `gh pr list --state open` must be empty or each open pull request must be listed in the log with its blocker, and `main` must be green.
- A section "Needs the owner" in the log collects every decision that is his: for example the 44 old commits on `main` that carry a `Claude-Session:` link in their message (not a co-author), which can only be removed by a force-push he must approve.

## 8. What "done" looks like at the end of the night

- All of T1 to T16 merged, plus any extra tests you found.
- At least features B1, B3, B4 and B5 merged; B2, B6, B7 and B8 merged if time allows.
- Every robustness bullet in section C has at least one merged test.
- `STATE.md` log current, `CHANGELOG.md` current, full suite green on CI, nothing unpushed.

## 9. Round 3: thirty more items (added 2026-11-27 after rounds 1 and 2 were finished)

Rounds 1 and 2 are merged: T1 to T16, failure injection for every cloud seat, the locked CSV appends and creation, `verify-quotes`,
`sunday`, `egress`, `dash-export`, the guard additions, the delegate reroute and the weekly Windows soak workflow. Same workflow, same
rules as above. Mark an item done in the log with its pull request number. Items marked (owner) need the owner's yes first: stop and log them.

### Reliability
1. A script `scripts/shuffle_run.py` that runs the test files in random order with a printed seed, to expose order dependence; run it three times.
2. A two-process test for `record_result` (task file, ledger row and run record in one commit): no row lost, no half commit.
3. What `store_lock` does when the lock is held longer than its timeout: a clear error naming the lock, covered by a test.
4. Crash recovery: kill a child process in the middle of `commit_transaction`, then prove `recover_journal` restores a consistent state.
5. `atomic_write_bytes` onto a destination another process holds open (Windows): the error names the path and the number of tries.
6. Disk-full injection for every writer module (study, log, decision, week, exam): no partial or empty file is left behind.
7. Performance budget: a 50 MB `runs.jsonl` must not make `earn`, `egress` or `sunday` take more than a few seconds.
8. Extend `tests/test_fuzz_logs.py` to ratings, predictions, experiments and vocabulary: CRLF, BOM, broken quotes, NUL bytes.
9. Clock tests around midnight UTC against local time for ledger dates and the 7-day windows.
10. `LIFEOS_HOME` with spaces, non-ASCII characters, a trailing slash and a relative path, across the main commands.

### Privacy
11. Guard: an `Authorization: Basic` header and a long hex or base64 value after `key=` or `secret=`; with harmless look-alikes that must stay clean.
12. A test that the pack sent to every cloud seat never contains `me.md` or `now.md` unless `--full` is given.
13. Redaction round trip: for every canary kind, `redact` then `guard` finds nothing.
14. `egress` warning when one seat's weekly tokens pass its share in `seats.SHARES`.
15. (owner) Bring the notes repo's own CI guard (`data_guard.py`) up to date with the engine guard.
16. A check that no module writes a prompt or answer text into the run ledger (only counts, ids and status).

### Seats and answer quality
17. `lifeos ask --failover`: an explicit opt-in that uses the delegate chain, with the same private-task rules.
18. Per-seat prompt tests: what each adapter sends (stdin or file) is the pack and nothing else.
19. Grok: refuse or warn when a URL in the task is not public https.
20. Seat health memory: if the last `doctor --smoke` is older than 7 days, `delegate` says so once.
21. `lifeos rate --undo`: remove the last rating of a task by mistake, with a test.
22. A warning when a rating of 2 or lower has no note.
23. An answer-length flag in the free check (a very long answer to an L0 task).
24. A prompt experiment harness: two wordings of `GROK_RULE` on the same three public questions, results recorded for the owner (needs the cloud; run only on the owner's word).

### Documentation and daily use
25. `lifeos help-me` prints the daily loop from `docs/DAILY.md`.
26. Shell completion covers every new command (extend the completion test).
27. Error-message audit: every `lifeos:` error says what to do next, checked by a test over the source strings.
28. `docs/COMMANDS.md` generated from the parser, with a staleness test like the architecture graph.
29. Cut release v0.5.1 from the Unreleased section once items 1 to 28 are merged: version bump, changelog move, tag. (owner: the tag and release publication)
30. Tidy `STATE.md`: group the log lines under dated headings and keep each under 400 characters, with a test on line length.

## 10. Round 4: thirty urgent items (added 2026-11-27, from what rounds 1 to 3 showed)

Same workflow and rules as above. Order matters: A first, because every later group depends on trusting the files. Items marked (owner) need the owner's yes.

### A. Trust the files (do these first)
1. A self-check command: one command that checks the ledger chain, `ratings.csv`, every task file, `waiting.json` and the run records; prints what to fix; exits non-zero on damage.
2. `lifeos task lint`: every task has a valid `status`, an `id` equal to its file name, a `done_when`, and a proof when it is `done`.
3. A backup command and a restore command: a dated zip of the logs and tasks kept on this laptop only, with a test that a restore gives back identical bytes.
4. A broken ledger chain names the first bad record and stops; it never repairs by itself.
5. A two-process test for `lifeos rate` and `lifeos unrate` on the same file: no lost or doubled row.
6. Count every `os.replace` retry in a small local counter file and show it in `doctor`, so the Windows error is measured, not guessed.
7. `dash-export` writes all its files or none (stage in a folder, then rename).
8. `ask` takes a `--run-id` and is idempotent on retry, as the MCP tools already are.

### B. Seats and answers
9. Classify seat failures (timeout, quota, sign-in, bad format) in the run record and show the split in `earn`.
10. `lifeos ask --dry-run`: print exactly what would be sent (pack and task) and what the guard says, send nothing.
11. `lifeos route` shows the seat with the best mean rating per kind, only when it has at least three ratings; advice, never a silent switch.
12. `lifeos today` lists answers older than a day that have no rating yet.
13. A local-seat retest script: three fixed public prompts for Qwen and Ollama, timings written to `docs/LIVE-CHECK.md`. (owner: run it after the RAM is in)
14. A warm-up command: load a local model once before use, so the first call is not the slow one. (owner: decide after the retest)
15. `doctor` shows each seat's rest-until time and last smoke test age.
16. Gemini and Codex answers cut off mid-sentence are flagged by the free check.

### C. Privacy
17. The ledger stores a hash of the pack that was sent, so you can prove later what left without keeping the text.
18. The guard also reads a seat's answer before it is saved to a task file; a secret in an answer is redacted and noted.
19. `egress --task <id>`: what left for one task.
20. A canary test: a fake secret planted in a task, a note and `me.md` must never reach any adapter's input.

### D. Better checks
21. Structured `done_when` parts the free check can test: a number, a file path that exists, a quoted line that is in the source.
22. When two seats answer the same task, flag numbers that differ between them.
23. `lifeos prove` adds the commit or pull request number when the proof is a merged change.

### E. Cockpit and daily use
24. `dash-export` also writes egress, latency, seats and the merged-PR list, so one command refreshes the whole cockpit.
25. `scripts/refresh_cockpit.py` runs the export and prints the exact upload steps and dataset names.
26. `today` shows waiting items with days left, from `waiting.json`.
27. `sunday` writes `reports/week-YYYY-WW.md`, so every week leaves a file.

### F. Test strength and release
28. Cut v0.5.1 from Unreleased. (owner publishes the tag and release)
29. Break-the-guard test: remove each guard pattern in turn and prove a test fails (every pattern is covered).
30. Seeded property tests for CSV round trip, task id parsing and date windows, with the seed printed on failure.


### Round 4 status (updated 2026-11-27 evening, after pull request 127)
- Built and merged: 1, 2, 3, 5, 6, 7, 9, 11, 12, 15, 16, 19, 20, 21, 22, 24, 25, 26, 27, 29, 30.
- Already in the engine before round 4 (checked, nothing to build): 4, 8, 10, 17, 18.
- Still open: 13 and 14 (owner, after the RAM is installed), 23 (ask the owner what the proof line should name), 28 (the v0.5.1 files are prepared; the owner publishes the tag and release).
- All pull requests are merged, the working tree is clean, and both repos match their remote main. Nothing is half done.

### Where to continue (written for the next model)
1. `git pull`, read `STATE.md`, then this file's sections 1 to 5 (rules, workflow, traps).
2. Run `lifeos selfcheck`, `lifeos today` and `lifeos sunday` in the notes repo: they show what needs attention now.
3. Continue from section 11 below. Every item there comes from something that really happened; do not invent a speculative round.
4. The cockpit (a private page) is refreshed with `python scripts/refresh_cockpit.py`; the owner or Claude uploads the files.
5. Never touch the paused side project. Never force-push. The owner publishes releases.


## 11. Round 5: twenty items from what really happened (written 2026-11-28)

Each item names the evidence. Same workflow and rules as above. Items marked (owner) need his yes or his hands.

### A. Close the Windows file-race family
1. A locked, retried read for every file the engine replaces atomically (tasks, ratings, ledger, waiting list). Evidence: pull request 131 found that two `ask` processes could still collide on a task file.
2. A test that starts three processes doing `ask`, `rate`, `task close` and `waiting add` on one home at once and finds no error and no lost row.
3. `lifeos selfcheck` prints, for each problem, the one command that fixes it (it still changes nothing).
4. `today` warns when the last `backup` is older than 14 days.

### B. Seats and answers
5. `earn` shows a calendar of usage-limit rests per seat. Evidence: Codex and Gemini both hit limits in one week.
6. After a call, `ask` prints how much of that seat's weekly share is used, from `egress`.
7. `rate` with no arguments walks through the unrated answers that `today` lists (a plain prompt per answer, no model call). Evidence: three answers still unrated.
8. (owner) Install the RAM, then run the local-seat retest and decide the warm-up (round 4 items 13 and 14).
9. A short answer-quality note per seat in `route` output, from ratings with at least three scores.

### C. Daily use
10. A "what is next" command: the one thing to do now, from `today`, with the exact command to run.
11. `lifeos task block ID --reason TEXT`, the twin of `task close`, for a task paused on purpose. Evidence: the paused side project was set by hand.
12. `help-me` and the shell completion list the new commands (`task close`, `waiting`, `selfcheck`); a test fails when they do not.
13. `waiting` entries with a date appear in `sunday`, with days left.

### D. Cockpit
14. `scripts/refresh_cockpit.py` also writes `shipped.json` from the merged pull requests (`gh pr list`), so that list is not typed by hand.
15. The cockpit's seat table (`seats.json`) is generated from `lifeos/seats.py`, so it cannot drift.

### E. Quality of the engine
16. Make the top three largest modules smaller (check `tests/test_budgets.py` for the ratchet) without changing behaviour.
17. Run `scripts/shuffle_run.py` three times after every ten merged pull requests and log the seeds in `STATE.md`.
18. A README quickstart test: every command shown in the first screen of `README.md` runs against the demo home without error.

### F. Release
19. (owner) Publish v0.5.1: the tag target is the merge of pull request 132 (commit 60d6c53); `main` has one later CI-only commit that belongs under Unreleased.
20. After 19, cut v0.5.2 from the round 5 work when items 1 to 7 are merged.


### Round 5 status (updated 2026-11-28, after pull request 143)
- Built and merged: 1 (locked, retried reads), 3, 4, 5, 6, 7 (`rate --walk`), 10 (`next`), 11 (`task block`), 12, 13, 14, 15, 16 (cockpit template moved out; `cockpit.py` is 515 lines), 18; also `task close` and `waiting` (not on the list, found needed).
- Item 2 (a three-process race test) is not built yet. Item 9 is covered by the `learned:` line of `route`. Item 17 is a routine: run `scripts/shuffle_run.py` from a separate worktree (switching branches during a run gives false failures) and log the seed in `STATE.md`.
- Owner items: 8 (RAM, then the Qwen retest), 19 (publish v0.5.1). Item 20 (v0.5.2) follows 19.

## 12. Round 6: small items from the same evidence (written 2026-11-28)
1. Done: two read-only MCP tools, `lifeos_selfcheck` and `lifeos_waiting_list`.
2. A three-process race test for `ask`, `rate`, `task close` and `waiting add` on one home (round 5 item 2).
3. `earn` shows rated against unrated answers per seat, so a seat with no ratings is not mistaken for a good one.
4. The weekly soak workflow also runs `selfcheck` on the demo home and the cockpit refresh script, so a broken helper is found on a schedule.
5. (owner) Ignore `.last-backup` in the notes repo, and decide whether old answers (three are unrated) get rated with `rate --walk` or are left.
6. Real use: run five new real tasks across the seats, rate each one, and let `sunday` show the result before any new feature is chosen.
7. (owner) After the RAM: Qwen retest, then v0.5.1 published, then v0.5.2 cut from rounds 5 and 6.


## 13. Round 7: thirty items from a full scan (written 2026-11-28; the owner was away and asked for a deep scan)

What the scan looked at: the installed package in a clean virtual environment, every command with `--help` and with no arguments (66 commands, no traceback), module and test coverage, function sizes (17 of 638 functions are over 60 lines; `build_parser` has 425), the real notes repo, the seat table, the first blind review of the new code (Gemini found five real bugs in it), and the owner's rules and deadlines in `now.md`. Same workflow and rules as above. Items marked (owner) need his yes or his hands.

### A. Packaging and release
1. Done: `lifeos demo` and `selftest` work after a plain `pip install` (the demo home is bundled; found in a clean virtual environment).
2. Done: `python -m lifeos` works (the module had no `__main__`).
3. Done: the release checklist and CI install the built wheel into a clean environment and run `demo` and `selftest`, so the next packaging miss is caught before a release.
4. Done: `tests/test_release_files.py` checks that `lifeos.__version__`, `pyproject.toml` and the newest released CHANGELOG heading agree.
5. Done: v0.5.1 was published from the merge of pull request 132, commit 60d6c53. The owner cuts v0.5.2 later from the Unreleased work.

### B. Review the new code (rule 7, blind)
6. Done: Gemini and Claude blind-reviewed `nextup`, `ratewalk`, the read retries in `store` and `today.coverage`; each finding was checked by hand. The real findings have regression tests and fixes. The bounded Windows read retry was deliberate and stayed unchanged.
7. Blind review of the `dash-export` rollback, `backup --restore` and `selfcheck`.
8. Done: `lifeos review` prints a plain summary when one reviewer fails and the others answer ("2 asked, 1 answered, codex rested"), keeps the usable answers and exits 4 for partial instead of 3 for failed.

### C. Seat health
9. Done: "out of credits" (HTTP 402) is a resting reason in `seats`, `doctor` and the `delegate` chain, with the message and no retry (pull request 155).
10. Done: `seats` shows the age of each seat's last good call, so a seat that has not answered for weeks is visible.
11. (owner) After the RAM: the Qwen retest and the warm-up decision.

### D. The real-use loop (the aim of the project)
12. Done: `today` and `next` read the `## Deadlines` section of `now.md` and show the next made-local action with days left, without copying the owner's dates into this public repo.
13. Done: `today` warns when the update marker in `now.md` is more than 14 days old.
14. `sunday` ends with one proposed small fix for the week (rule 11), chosen from the numbers: the kind with the lowest ratings, the unrated answers, the slowest seat, an unused part.
15. `earn` writes the "did it earn its place" question for each unused part (`vocab`, `decide` and `debate` were never used in 30 days) so the Sunday review can answer it. (owner decides pause or remove)
16. Run five more real tasks across the seats, rate each one, and keep the numbers in `sunday` (ongoing).

### E. Quality and tests
17. Split `build_parser` (425 lines) into one registration function per command group, with no change in behaviour (the help text is checked by the commands page test).
18. Split `run_review` (217 lines) into steps; the existing tests must pass unchanged.
19. A test that every module is imported by at least one test (the scan found `cockpit_page` the only one without), kept as a permanent check.
20. A sample-per-flag test for the free answer check, like the guard's: each flag has a text that raises it and a near miss that does not.
21. Seeded property tests for `days_left`, `sunday.week_file` and the ISO week around new year.
22. `selfcheck` also reads predictions, experiments, vocabulary and decisions, not only the ledger, tasks, ratings and waiting list.
23. A test that `task new` and `task close` refuse a secret on the command line the way the MCP tool does.

### F. Documentation and the owner
24. `docs/COCKPIT.md`: what the cockpit page shows, the seven datasets, and the exact refresh steps (today only the script's help says it).
25. `docs/README.md`: an index of every document in `docs/` with one line each, so a new model finds the right one.
26. `STATE.md` and this file get a "next 5 actions" block that a script (`scripts/open_items.py`) prints from the status lines, so the order is never guessed.
27. (owner) Decide the 44 commits on public `main` that carry a session link in the message, the `dependabot[bot]` entry, and the 50 merged remote branches.
28. (owner) Rate the three old unrated answers with `rate --walk`, or decide to leave them.
29. (owner) Ignore `.last-backup` in the notes repo and add `lifeos next` to the morning routine.
30. Keep the shuffled-order run (from a separate worktree) as a routine after every ten merged pull requests, and log the seed in `STATE.md`.


## 14. Hand-off from Claude, continued by Codex (read this first; it is the newest)

Run `git pull`, then `gh pr list` and `lifeos selfcheck` and `lifeos today` in the notes repo. They show the true state; this section says what it was when Claude stopped.

### Done (all merged on `main` unless a pull request is named under "Open")
- **v0.5.1 is released**: tag `v0.5.1` on commit `60d6c53` (the merge of pull request 132), GitHub release published 2026-11-27. `main` has moved on since; the later work is under `Unreleased` in `CHANGELOG.md` for v0.5.2.
- **Round 4** (30 items): 26 built or already present. **Round 5**: all but the owner's items. **Round 6**: items 1 to 4 built. Details and status lines are in sections 10 to 12.
- New commands: `selfcheck`, `next`, `waiting add|list|done`, `task close`, `task block`, `rate --walk`, `backup --restore`, `sunday --save`, `python -m lifeos`; `today` shows unrated answers, days left on waiting items, an overdue backup; `earn` shows why calls failed and the days a seat hit a usage limit.
- Safety: a break-the-guard test (every privacy pattern proven to matter), a canary test (private files never reach a cloud seat), a four-process race test, seeded property tests, typed text is guarded with the owner's private patterns and the `lifeos-guard: allow` marker cannot exempt it.
- Windows: readers wait out a short file lock (`store.read_bytes_retry`, `read_text_retry`); the write retry has seven tries. This may be the cause of the old unexplained write error; the weekly soak will show.
- Packaging: after a plain `pip install` the demo and `selftest` work (the demo home is bundled in `lifeos/_demo_home`, kept identical to `examples/demo-home` by a test).
- Blind review (rule 7) of the new code: Gemini and Codex each reviewed `task close` and `waiting`; 10 of 10 findings were real and are fixed.
- The cockpit page (a private page, not in this repo) was redesigned and its data refreshed; refresh it with `python scripts/refresh_cockpit.py`.
- Round 7 (section 13): the 30-item list from a full scan is written. Item 6's blind review is complete and its confirmed findings are fixed; item 9's no-credits seat handling is merged in pull request 155.

### Open at the time of writing
- The engine hardening branch for round 7 item 6 is the only work in progress. Merge it only after the full suite, guard and all CI checks pass.
- Notes repo pull request **#64** is merged. The durable item 6 review task will be closed with the engine merge as proof.

### Not done (in order of value)
1. Round 7 item 7: blind-review the `dash-export` rollback, `backup --restore` and `selfcheck`; check each finding by hand and write a failing test before each real fix.
2. Round 7 items 14, 15 and 17 to 23 (see section 13). Items 3, 4, 12 and 13 are already built and covered by tests or CI.
3. Run real tasks across the seats and rate them (`rate --walk`); `sunday` shows how few answers are rated.

### Owner's items (never do these without his word)
- Install the RAM, then retest Qwen and Ollama and decide the warm-up (round 4 items 13 and 14).
- Grok has no credits (402): he must check the subscription.
- Decide about the 44 old commits on public `main` that carry a session link in the message (a force push would be needed; never do it yourself), the `dependabot[bot]` entry on the paused side project, and the 50 merged remote branches.
- Ignore `.last-backup` in the notes repo; rate or drop the three old unrated answers.
- Publish v0.5.2 later: cut it from the Unreleased section once the round 5 to 7 work is merged.

### Traps learned on 2026-11-27 and 28 (each cost a CI round or nearly a leak)
- **Never put the owner's real dates, permits, exams or any personal fact in the public repo**, not in tests, the changelog or this file. Use made-up examples ("pay the invoice"). A line of this kind was nearly merged and had to be removed.
- A new module needs an entry in `LAYER` (`tests/test_layering.py`); regenerate `docs/ARCHITECTURE-GRAPH.md` (`lifeos arch --write ...`) and `docs/COMMANDS.md` (`lifeos commands --out ...`) after any import or command change, or CI fails.
- `CHANGELOG.md` conflicts on nearly every pull request; keep both sides and make sure no conflict marker is left (`git grep "^<<<<<<< "`).
- Do not run the shuffled full test run while switching branches; use a separate worktree (`git worktree add --detach ../tmp origin/main`) and set `PYTHONPATH` to it.
- When a test asserts an exact phrase in output, the temp folder name of the test can contain words that match; assert on a longer unique prefix.
- Generated text with backslashes written through a shell here-document can be mangled; edit with the editor tool or build the characters with `chr(92)`.
- A pull request whose base was merged under it needs `git merge origin/main` before its checks mean anything.
- Seats: Codex had a usage limit on 2026-11-27 (it said to try again at 17:14), Grok returned 402 (no credits), local models are slow until the RAM arrives. `lifeos seats` and `lifeos doctor` show the state.
