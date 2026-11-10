# LifeOS Engine: instructions for Claude Code
- Python 3.10+, standard library only. No new dependency without a written reason in the pull request.
- Tests first for every behaviour change. Before you finish: `pytest -q` and `lifeos guard $(git ls-files)`.
- This repo goes public from v0.3: no personal data, ever. Everything in examples/ is made up.
- One module per command; keep functions short; update README.md when a command changes.
- Work on a branch; the owner merges. Short answers; diffs, not whole files.
