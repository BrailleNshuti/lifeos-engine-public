# State of lifeos-engine · 2026-11-19

Read this first. Keep it short; update it after meaningful merges.

## Now

- Version 0.4.1. Commands are listed in README.md; the roadmap is there too.
- Seats: one table (`lifeos/seats.py`) with failover, one cloud budget and rest-until logic that reads absolute and relative reset times.
- `lifeos doctor --smoke [--only a,b]` probes seats, prints why a probe failed and rests seats that hit a usage limit. A smoke record never counts as spend.
- Prompt Lab runner (`lifeos lab check/pack/score`) is offline: no model, no network.
- `lifeos debate` (merged): blind three-round debate scored by rules; protocol in `docs/DEBATE.md`. `debate run` calls the seat adapters directly (not `delegate`) so the exact prompt is provable. One live run on 2026-11-19: see `docs/DEBATE-LIVE-RUN.md`.
- Privacy guard (`lifeos guard`) blocks identifiers and keys; CI runs it on every tracked file.
- No personal data in this repo; everything in `examples/` is made up.

## Open

- The v0.4.0 tag still crashes on `lifeos --help` (a bare `%` in one help string; per-command `--help` works). Fixed in v0.4.1; use that release.
- Windows write flake (measured 2026-11-20): 2 of 3 full runs failed, 3 failed `os.replace` calls in all, each `PermissionError` winerror 5, single-threaded, not held by this process, no holder visible a moment later, always on a file just copied or written (`copytree` of the demo home, then `tasks/*.md`, `logs/runs.jsonl`, `logs/ledger.csv`). Consistent with a short handle taken by an outside scanner or indexer; not proven. The two tests once blamed on a temporary revert (`test_delegate`, `test_durable_kernel`) fail the same way. `lifeos/diag.py` now records every such failure (`LIFEOS_REPLACE_DIAG=<file>`). Fix on `fix/replace-transient-retry`: `store._replace` retries only winerror 5/32, five pauses (0.77 s in all), original error re-raised. After it: 3 of 3 full runs clean (779 passed each), but zero `recovered` events, so the retry was never exercised and 3 clean runs could be luck (about a quarter chance at the old rate). Check again over more runs (`LIFEOS_REPLACE_DIAG=<file>`, count `recovered` vs `failed`).
- `debate` evidence gate checks for a pointer, not truth: a seat that says it ran a test is counted, one that says it could not is not. Documented in `docs/DEBATE.md`; seen live.
- Public docs still cite private plan sections ("Section 8.2", "Section 10.3") in README, CLI help, docstrings and MCP descriptions, and the README row for `route` says "work-lane check".
- Live proof of the Grok seat flags is still to be recorded after its usage resets.
- External CLIs need a periodic `--smoke` run; an empty working directory is not an operating-system sandbox.

## Next

- Use the engine on real tasks, record corrections and failed calls, then choose the next feature from those numbers.
