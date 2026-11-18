# State of lifeos-engine · 2026-11-17

Read this first. Keep it short; update it after meaningful merges.

## Now

- Version 0.4.0. Commands are listed in README.md; the roadmap is there too.
- Seats: one table (`lifeos/seats.py`) with failover, one cloud budget and rest-until logic that reads absolute and relative reset times.
- `lifeos doctor --smoke [--only a,b]` probes seats, prints why a probe failed and rests seats that hit a usage limit. A smoke record never counts as spend.
- Prompt Lab runner (`lifeos lab check/pack/score`) is offline: no model, no network.
- Privacy guard (`lifeos guard`) blocks identifiers and keys; CI runs it on every tracked file.
- No personal data in this repo; everything in `examples/` is made up.

## Open

- Live proof of the Grok seat flags is still to be recorded after its usage resets.
- External CLIs need a periodic `--smoke` run; an empty working directory is not an operating-system sandbox.

## Next

- Use the engine on real tasks, record corrections and failed calls, then choose the next feature from those numbers.
