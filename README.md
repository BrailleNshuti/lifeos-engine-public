# LifeOS Engine

The machinery of a personal AI operating system: one shared memory that Claude, Codex, ChatGPT and Grok all work from, plus the tools that keep it honest, cheap and private.

The engine is code only. Your life lives in a separate **private data repo** (`lifeos`): rules, profile, current week, task files, logs and reviews. The engine reads it through `LIFEOS_HOME`; nothing personal is ever stored here, and everything in `examples/` is made up.

## What v0.1 does

| Command | What it does | Why it matters |
|---|---|---|
| `lifeos task new "<one sentence>"` | Creates `tasks/T-YYMMDD-name.md` from the hand-off template; you only write the done-when line | Hand-offs between models in seconds, never overwrites a file |
| `lifeos task list [--status doing]` | Lists task files with status and due date | One look at open work |
| `lifeos week [--week 2026-W47]` | Proofs and net time saved from the logs, as the start of the Sunday review | Numbers come from data, never from a model's guess |
| `lifeos context [TASK] [--budget 6000]` | Prints rules, the task, now and me in priority order, trimmed to a token budget | Paste once, pay little; shows the token cost before you send |
| `lifeos ask <model> <task> [--budget N] [--full] [--dry-run]` | Guards the context pack (task and rules only; `--full` adds now.md and me.md), sends it to that model (codex, gemini, claude or ollama) through its command-line tool (ollama: local address), appends `## Result · <model> · <date>` to the task file and one ledger line. A guard BLOCK sends nothing (exit 1); a missing tool exits 2 | Work moves between models without copy and paste, and off the Claude limit |
| `lifeos guard [files] / --staged` | Blocks IBANs, card numbers, ID and passport numbers, keys and private keys; warns on emails, phone numbers and possible secrets | Class C data never reaches a repo |
| `lifeos doctor` | Checks the data repo and shows how many tokens its always-loaded files cost | Keeps the core small |

Five portable skills (open Agent Skills format, read by Claude and Codex) live in `skills/`: `lifeos-task`, `weekly-review`, `decision-memo`, `usage-handoff` and `work-prompt`.

## Quick start (Windows PowerShell or any shell)

```
pip install -e .                      # from this folder; standard library only
$env:LIFEOS_HOME = "C:\path\to\lifeos" # bash: export LIFEOS_HOME=~/lifeos
lifeos doctor
lifeos task new "Draft the iwa demo checklist"
lifeos week
lifeos context T-261116 --budget 4000
```

Install the skills for Claude Code and Codex: `scripts/install-skills.ps1` (or `scripts/install-skills.sh`).
Install the privacy guard as a pre-commit hook in the data repo: `scripts/install-hook.sh C:\path\to\lifeos` (Git Bash).

Private patterns that must never be committed (your street, your phone number) go in `~/.lifeos/private-patterns.txt`, one regular expression per line, outside every repo. Mark a false alarm with `lifeos-guard: allow` on that line.

## Checks

```
pytest -q
lifeos guard $(git ls-files)
```

CI runs both on every push and pull request.

## Roadmap

| Release | Target | Adds |
|---|---|---|
| v0.1 | Nov 2026 | Task files, weekly numbers, context packs, privacy guard, doctor, five skills, CI |
| v0.2 | Gate 1, 6 Dec 2026 | Scoreboard from all logs, context packs per tool, the scheduled weekly review using these commands |
| v0.3 | Gate 2, 17 Jan 2027 | Prompt Lab runner: prompt cards with test cases run through `claude -p` and `codex exec`, scored; repo goes public |
| v0.4 | Gate 3, 28 Mar 2027 | Dashboard from the logs; GitHub Actions pipeline |
| v0.5 | Jun 2027 | Model router (LangGraph, LiteLLM budgets) evaluated on 50 real tasks |
| v1.0 | Nov 2027 | Hardening, evaluation report and public case study |

## Rules for this repo

Standard library only unless a pull request explains why. Tests first. No personal data, ever. Work on a branch; the owner merges.

Licence: to be chosen before the repo goes public.
