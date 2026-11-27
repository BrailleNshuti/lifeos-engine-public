# Handoff: continue building the engine (written 2026-11-27, for any coding model, first for Codex)

The previous model ran out of usage. You take over now. The owner wants 8 to 9 hours of continuous, careful work, no idle gaps,
and every step saved to GitHub so the next model can see exactly where you stopped. Read this whole file before you touch anything.

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
- Keep a log in `STATE.md` under the bullet "Overnight log". After every merged item or every hour, whichever comes first, add one factual line: time, pull request number, what changed, what failed, what is next. Push it through a docs pull request.
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

