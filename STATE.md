# State of lifeos-engine · 2026-11-19

Read this first. Keep it short; update it after meaningful merges.

## Now

- Version 0.4.0. Commands are listed in README.md; the roadmap is there too.
- Seats: one table (`lifeos/seats.py`) with failover, one cloud budget and rest-until logic that reads absolute and relative reset times.
- `lifeos doctor --smoke [--only a,b]` probes seats, prints why a probe failed and rests seats that hit a usage limit. A smoke record never counts as spend.
- Prompt Lab runner (`lifeos lab check/pack/score`) is offline: no model, no network.
- `lifeos debate` (branch `feat/debate`, PR open): blind three-round debate scored by rules; protocol in `docs/DEBATE.md`. `debate run` calls the seat adapters directly (not `delegate`) so the exact prompt is provable; not yet run on a real question.
- Privacy guard (`lifeos guard`) blocks identifiers and keys; CI runs it on every tracked file.
- No personal data in this repo; everything in `examples/` is made up.

## Open

- The published v0.4.0 tag crashes on `lifeos --help` (a bare `%` in one help string; per-command `--help` works). Fixed on `fix/top-level-help`, with tests; a patch release is the owner's call.
- One full test run on Windows hit a `PermissionError` from `os.replace` in `store.atomic_write_bytes` (once; passes alone; cause not proven). Next: log the Windows error code and paths on failure before adding any retry.
- `lifeos delegate` (and probably `ask`) crash with `UnicodeEncodeError` when stdout is redirected to a file on Windows and the answer holds a character outside cp1252 (for example `≤`). The answer is still saved in the task file. Found 2026-11-19; not fixed yet.
- Public docs still cite private plan sections ("Section 8.2", "Section 10.3") in README, CLI help, docstrings and MCP descriptions, and the README row for `route` says "work-lane check".
- Live proof of the Grok seat flags is still to be recorded after its usage resets.
- External CLIs need a periodic `--smoke` run; an empty working directory is not an operating-system sandbox.

## Next

- Use the engine on real tasks, record corrections and failed calls, then choose the next feature from those numbers.
