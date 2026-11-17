# Changelog

Dates are release dates. Newest first.

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
