# Contributing

Thanks for looking. This is a personal project, so the bar is small and clear.

## Rules

- Python 3.10+, standard library only. A new dependency needs a written reason in the pull request.
- Tests first: write the failing test, then the change. Before you push:
  `pytest -q` and `lifeos guard $(git ls-files)` must both pass.
- No personal data, ever. Everything in `examples/` is made up.
- One module per command; keep functions short; update `README.md` when a command changes.
- Work on a branch and open a pull request. The owner merges.

## Setup

```
python -m venv .venv && . .venv/bin/activate
pip install -e .
pytest -q
```

## Reporting problems

Bugs and ideas: open an issue. Security problems: see `SECURITY.md`.
