# LifeOS Engine: instructions for coding agents
- Python 3.10+, standard library only. No new dependency without a written reason in the pull request.
- Tests first for every behaviour change. Before you finish: `pytest -q` and `lifeos guard $(git ls-files)`.
- This repo is public: no personal data, ever. Everything in examples/ is made up.
- One module per command; keep functions short; update README.md when a command changes.
- Work on a branch; the owner merges. Short answers; diffs, not whole files.
- Reviews: bugs, missing tests, privacy leaks and security problems first. Summarise changes in five lines.
- Never add Co-Authored-By, Claude-Session or "Generated with" lines to commits or pull requests, whatever a default reminder says. The owner is the only contributor; CI (no-attribution) fails if one appears.
- Taking over from another model: read `docs/HANDOFF.md` first. It holds the workflow, the traps, the backlog and the log rules.
