# LifeOS Engine

The machinery of a personal AI operating system: one shared memory that Claude, Codex, ChatGPT and Grok all work from, plus the tools that keep it honest, cheap and private.

The engine is code only. Your life lives in a separate **private data repo** (`lifeos`): rules, profile, current week, task files, logs and reviews. The engine reads it through `LIFEOS_HOME`; nothing personal is ever stored here, and everything in `examples/` is made up.

## What v0.1 does

| Command | What it does | Why it matters |
|---|---|---|
| `lifeos task new "<one sentence>" [--route R] [--level L2] [--due 2026-11-30]` | Creates `tasks/T-YYMMDD-name.md` from the hand-off template (route defaults to `Claude Code -> Codex review`, level to `L2`, one of L0 to L3); you only write the done-when line | Hand-offs between models in seconds, never overwrites a file |
| `lifeos task list [--status doing]` | Lists task files with status and due date | One look at open work |
| `lifeos week [--week 2026-W47] [--json]` | Proofs and net time saved from the logs, plus a `Delegation:` line with model calls and flagged answers, as the start of the Sunday review; `--json` prints the numbers as JSON (the Delegation part as `delegation`) | Numbers come from data, never from a model's guess |
| `lifeos context [TASK] [--budget 6000]` | Prints rules, the task, now and me in priority order, trimmed to a token budget | Paste once, pay little; shows the token cost before you send |
| `lifeos ask <model> <task> [--budget N] [--full] [--dry-run]` | Guards the context pack (task and rules only; `--full` adds now.md and me.md), sends it to that model (codex, claude, ollama, qwen, or gemini through Antigravity `agy`) through its command-line tool (ollama and qwen: the local Ollama address), appends `## Result · <model> · <date>` to the task file and one ledger line (its note ends with `flags: N`, the count from the free answer check). A guard BLOCK sends nothing (exit 1); a missing tool exits 2 | Work moves between models without copy and paste, and off the Claude limit |
| `lifeos delegate <task> [--model M] [--budget N] [--full] [--dry-run]` | Claude is the lead: picks the best-fitting model from the task text (private sorting -> qwen, code -> claude writes and codex tests and reviews, learning -> codex, long reading and live facts -> gemini, plans and decisions -> claude), runs it through `lifeos ask`, prints the answer plus a free CHECK line (no model call: empty or too short, refusal, echoed prompt, success without evidence, undated link, guessing, no next step). A missing tool falls back to the next model and says so (a private task, qwen or ollama, never falls back to a cloud model: it stops); a failed call is shown, never retried elsewhere | One command (or one chat tool call) instead of choosing a model by hand |
| `lifeos sort-csv <file> [--out F] [--column C] [--categories a,b]` | Adds `lifeos_category` and `lifeos_check` columns to a bank CSV. Fully local: keyword rules first, then local Qwen for the rest; refuses a non-local Ollama address, never overwrites, never writes inside a git repo, prints counts only. The first line must be a header (it decides the delimiter; it is never printed in an error). Rows the model could not place (it answered `other`, or its answer was wordy or outside the list) say `yes` in `lifeos_check`; rows placed by the keyword rules never do | Your spending sorted without bank data touching any cloud or chat |
| `lifeos mcp` | Runs a local MCP server (standard library only) with six tools: list tasks, new task, context, write result, ask, delegate. Writes go through the privacy guard and stay inside tasks/ and the ledger | Chat apps read and write your task files with no copy and paste |
| `lifeos guard [files] / --staged` | Blocks validated IBANs/cards, contextual ID numbers, known key formats, private keys and assigned secrets; warns on emails and phone numbers. `--staged` scans the staged version; UTF-16 and legacy text are scanned | Catches high-confidence leaks before a commit; it is a backstop, not a complete classifier |
| `lifeos doctor` | Checks the data repo; fails when the always-loaded core is over 2000 tokens or a file is too long | Keeps the core small |

The `Delegation:` line of `lifeos week` judges models by numbers: it counts this week's `lifeos ask` ledger lines (`delegate` and `mcp` write them too) per model, most used first, and how many of those answers the free check flagged; the ledger keeps only that count, never the answer or the flag texts.

Two options go before the command name: `--home <path>` picks the data repo (default: `LIFEOS_HOME`, else the current folder, which must hold `now.md`); `--version` prints the version.

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

Install the skills for Claude Code, Codex and Antigravity/Gemini: `scripts/install-skills.ps1` (or `scripts/install-skills.sh`).
Install the privacy guard as a pre-commit hook in the data repo: `scripts/install-hook.ps1 C:\path\to\lifeos` (or `scripts/install-hook.sh C:/path/to/lifeos` in Git Bash).

Private patterns that must never be committed (your street, your phone number) go in `~/.lifeos/private-patterns.txt`, one regular expression per line, outside every repo. Mark a false alarm with `lifeos-guard: allow` on that line.

## Security boundaries

- `ollama` and `qwen` refuse any `OLLAMA_HOST` that is not `localhost`, `127.0.0.1` or `::1`.
- The allow marker works only for reviewed file scans; outbound context and model answers cannot exempt themselves.
- The guard cannot reliably recognize natural-language health, tenant or employer information. Those remain policy rules: do not put them in a task or context pack.
- Model CLIs run in an empty temporary working directory, which reduces accidental context but is not an operating-system sandbox. Keep CLI permissions narrow and review each tool's configuration.

## Checks

```
pip install pytest                    # once, for the tests only
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

## Chat apps without copy and paste (`lifeos mcp`)

Claude Desktop: add this to `claude_desktop_config.json` under `mcpServers`, then restart the app.
Use your own path for LIFEOS_HOME.

```json
"lifeos": {"command": "python", "args": ["-P", "-m", "lifeos.cli", "mcp"], "env": {"LIFEOS_HOME": "C:\\Users\\you\\lifeos"}}
```

Claude Code: `claude mcp add -s user lifeos -e LIFEOS_HOME=<path> -- python -P -m lifeos.cli mcp` (`-P` keeps a `~/lifeos` data repo folder from shadowing the `lifeos` package when the app starts in `~`).
Other MCP apps (Codex, agy) use the same program (`python -P -m lifeos.cli mcp`) and `LIFEOS_HOME` environment variable.
`lifeos_ask` can take minutes; some apps stop waiting after about a minute. Screenshots stay in the chat.

## Claude as the lead

Register `lifeos mcp` in Claude (Desktop or Code). The server tells Claude its role: for work that fits another model it calls `lifeos_delegate`, reads the answer that comes back in the same chat, checks it against rules.md and writes the decision into the task file. You only talk to Claude.

Qwen runs locally through Ollama: `ollama pull qwen2.5:3b` (default). Pick another size with `LIFEOS_QWEN_MODEL`, for example `qwen3:8b` once the laptop has the RAM. `lifeos ask ollama` uses `LIFEOS_OLLAMA_MODEL` (default `llama3.2`); both talk to `OLLAMA_HOST` (default `http://localhost:11434`). Reasoning blocks (`<think>`) are stripped from local answers.

