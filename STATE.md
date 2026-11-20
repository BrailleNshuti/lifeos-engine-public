# State of lifeos-engine · 2026-11-20

Read this first. Keep it short; update it after meaningful merges.

## Now

- Released: **v0.4.1** (tag and GitHub release; it fixes the `lifeos --help` crash that v0.4.0 has). `main` is ahead of it, unreleased.
- Merged since 0.4.1 (all through pull requests with green CI on Linux and Windows): the new command `lifeos debate` (blind three-round debate scored by rules, protocol in `docs/DEBATE.md`) with a per-seat scorecard (`score --reveal`), a `debate` row in `lifeos earn`, a debate round trip in `lifeos selftest` (44 steps), a retry on short Windows sharing violations in `store._replace`, failure diagnostics for `os.replace` (`lifeos/diag.py`), output that no longer crashes on cp1252 (`lifeos/console.py`), answers that are no longer lost when a CLI's temp folder cannot be deleted, a release-bump proposal fixed, and private-plan references removed with a test that keeps them out.
- Seats: one table (`lifeos/seats.py`) with failover, one cloud budget and rest-until logic. `debate` records count toward the budget; pasted answers do not.
- `lifeos debate run` calls the seat adapters directly (not `delegate`) so the exact prompt sent is provable. Two live runs with Claude, Codex and Gemini: `docs/DEBATE-LIVE-RUN.md`.
- Privacy guard blocks identifiers and keys; CI runs it on every tracked file. No personal data in this repo; `examples/` is made up.

## Open

- **Windows write flake:** before the retry, 2 of 3 full runs failed on `os.replace` (winerror 5, single thread, no holder visible, always a just-written file; most likely a scanner or indexer, not proven). After it: 3 of 3 clean, but the retry was never exercised, so that is suggestive only. Keep measuring: run the suite with `LIFEOS_REPLACE_DIAG=<file>` and count `recovered` against `failed` events.
- **`debate` seats concede, they do not rebut:** two live runs, zero OPEN verdicts. The evidence gate checks that a pointer exists, not that it is true: a seat that says it ran a test is counted, one that says it could not is not. The Claude seat runs without a shell. Whether a different prompt changes this is untested.
- **Local full test runs:** the system once killed a 5-minute run for low memory and asked me not to restart it, so I relied on CI for the full suite on the later changes. Focused local tests passed each time.
- **Yours to decide, public already:** `lifeos/cockpit.py` hardcodes personal study targets (a language exam and its dates) and weekly bets; `skills/iwa-demo-check` names a personal side project; about 50 merged remote branches are not deleted.
- Live proof of the Grok seat flags is still to be recorded after its usage resets. External CLIs need a periodic `--smoke` run; an empty working directory is not an operating-system sandbox.
- I could not read `/usage` from inside the session, so the 75 % guard was not measurable; I used the seat table as a proxy, and my review calls ran from a throwaway home, so they are not in your real budget ledger.

## Decision for the owner: the next release

- Unreleased: the new command `lifeos debate` and the fixes above. `lifeos release` proposes **0.5.0** (a new command means minor).
- That collides with the roadmap, where v0.5 is the model router (Jun 2027). Options: **0.5.0** and move the router to a later row; or **0.4.2** and accept that a patch holds a new command. I did not publish either: the number and the roadmap are yours (rule 8). To release: bump `pyproject.toml` and `lifeos/__init__.py`, move `[Unreleased]` under the new heading in CHANGELOG, tag the merge commit, publish the GitHub release with the notes.

## Next

- Use the engine on real tasks, record corrections and failed calls, then choose the next feature from those numbers.
- Ideas I have not built: a `lifeos_debate` MCP tool so a chat can run a debate; a prompt experiment to see whether seats ever rebut with evidence; an `earn`-style soak script for the write flake.
