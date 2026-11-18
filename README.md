# LifeOS Engine

The machinery of a personal AI operating system: one shared memory that Claude, Codex, ChatGPT and Grok all work from, plus the tools that keep it honest, cheap and private.

The engine is code only. Your life lives in a separate **private data repo** (`lifeos`): rules, profile, current week, task files, logs and reviews. The engine reads it through `LIFEOS_HOME`; nothing personal is ever stored here, and everything in `examples/` is made up.

## What v0.1 does

| Command | What it does | Why it matters |
|---|---|---|
| `lifeos task new "<one sentence>" [--route R] [--level L2] [--due 2026-11-30]` | Creates `tasks/T-YYMMDD-name.md` from the hand-off template (route defaults to `Claude Code -> Codex review`, level to `L2`, one of L0 to L3); you only write the done-when line | Hand-offs between models in seconds, never overwrites a file |
| `lifeos task list [--status doing]` | Lists task files with status and due date | One look at open work |
| `lifeos week [--week 2026-W47] [--draft] [--redteam] [--json]` | Proofs, net time saved, logged hours (`hours.csv`) and daily health averages (`health.csv`) from the logs, plus a `Delegation:` line with model calls and flagged answers; `--draft` creates `reviews/<week>.md` without overwriting; `--redteam` prints a facts-only Red-Team pack (Section 10.2 item 6) | Numbers come from data, never from a model's guess |
| `lifeos log {proof,ledger,health,hours} ... [--date YYYY-MM-DD]` | Appends one validated, guard-checked, UTF-8/LF row to `logs/proofs.csv`, `logs/ledger.csv`, `logs/health.csv` or `logs/hours.csv` under the store lock; refuses duplicate consecutive rows, out-of-range numbers and privacy guard hits | Fast, corruption-proof daily logging without manual CSV editing |
| `lifeos runs [--status S] [--model M] [--task ID] [--limit N] [--json]` | Inspects the execution audit trail in `logs/runs.jsonl`: filters by status (`ok`, `failed`, `timeout`, `blocked`, `tool_missing`, `partial`), model or task prefix, and summarizes status counts, average duration and token usage | Immediate visibility into every model call, failure and blind review without opening raw JSONL |
| `lifeos kaizen [--month YYYY-MM] [--draft] [--json]` | Monthly System Health & Kaizen loop (Section 10.3): analyzes the last 28 days of logs and `system/changes.md` to answer the 5 System Health questions and optionally draft `reviews/<YYYY-MM>.md` | Self-improving rules backed by measured 4-week trials |
| `lifeos route <task_or_text> [--tier T] [--full] [--json]` | Evaluates all 6 questions of Section 8.2 routing (work-lane check, Tier-0 script check, 5-tier data policy, model matrix, L0–L3 blind review requirement, and weekly token/call budget guard) | Deterministic routing decisions before spending tokens |
| `lifeos cockpit [--export FILE] [--serve] [--port 8765]` | Exports or serves the private **Study Atelier** (`#learning`, `#study`, `#practice`, `#exam`, `#mastery`) with a focus contract, source library, verified recall queue, exam forge, recovery mode and evidence shelf | Makes learning the default experience; project and agent machinery stay secondary |
| `lifeos study {sources,import,bank,verify,attempt,exam}` | Imports guarded notes, generates source-grounded question candidates, records human verification and retrieval intervals, and freezes printable mock papers with separate answer keys | Turns notes into trustworthy practice without sending study content to a model or hiding fabricated answers in the static Cockpit |
| `lifeos context [TASK] [--budget 6000] [--explain]` | Prints rules, the task, now and me in priority order, trimmed to a token budget; `--explain` shows which files were included, trimmed or excluded, their token cost and SHA-256 fingerprint | Paste once, pay little; shows the token cost and provenance before you send |
| `lifeos ask <model> <task> [--budget N] [--full] [--run-id ID] [--dry-run]` | Generates a pre-execution `run_id`, guards the context pack, sends it to that model (codex, claude, ollama, qwen, or gemini through Antigravity `agy`), and commits the task result, ledger row and run record (`logs/runs.jsonl`) in one locked, journal-recoverable transaction. Also logs blocked, failed, timed-out and missing-tool runs with secret redaction | Work moves between models with retry idempotency, crash recovery and a complete audit trail. Notes listed under `## Context` (`.md` or `.txt` inside the data repository, up to four, never under `logs/` or `.git`, never outside it) are attached to the pack and shown by `--dry-run` |
| `lifeos delegate <task> [--model M] [--budget N] [--full] [--dry-run]` | Picks the open seat from one table (`lifeos/seats.py`): Qwen for private, sensitive and small local jobs; Claude writes code, plans and decisions; Codex tests, reviews, German and exams; Gemini does long reading and research; the locked Grok seat answers live facts (prices, news, today) with a source and a date (headless, JSON out, empty temp folder, no plan mode or subagents, at most 3 agent turns, unapproved tools refused with `dontAsk`, prompt passed in a private temp file; never selected for sensitive work, never with `--full`). Every seat gets the same prompt: one instruction plus one context pack. One cloud budget: a seat's limit is the lower of its 7-day share (Claude 40k, Codex 40k, Gemini 30k, Grok 20k) and what the weekly cap (120k tokens, 80 calls for all cloud seats) has left; a seat at its limit, or at its 24-call cap, is skipped. A usage-limit message rests the seat until the time it names: converted when it names a zone, read as UTC and flagged when it does not, a relative wait ("Resets in 78h40m32s", "try again in 45 minutes") is counted from the failure; 12 h when it names no time or one before the failure; capped at 8 days. A missing tool or failed call is replaced by the next open seat and the reason is written under `## Route` (not sent to the next model). A local or sensitive task never moves to a cloud seat. Flags: `degraded` when a small local model answered where a cloud seat was meant to; `check pending` when the checking seat is resting, missing, or is the one that wrote it. Prints the answer plus a free CHECK line | One command instead of choosing a model by hand; one provider running out does not stop the task, and nothing is skipped in silence |
| `lifeos seats [--json]` | One row per seat: 7-day tokens against its one limit, resting reason, replacement seat | See at a glance who is open and who takes over |
| `lifeos review <task> [--reviewers codex,claude] [--repo PATH] [--commit SHA] [--run-id ID] [--budget N] [--dry-run]` | Runs an independent blind review (rule 7) across multiple models on the same pre-committed facts-only pack (stripping prior `## Result` blocks). With `--repo`, embeds the exact 40-char commit SHA, branch, tracked file list and unified diff into the pack and runs reviewer CLIs inside an isolated detached `git worktree` at that commit; records both child `review` records and the parent `review_group` record (including partial/failed states) in `logs/runs.jsonl` | Multi-model verification on the exact repository commit without echo-chamber bias |
| `lifeos sort-csv <file> [--out F] [--column C] [--categories a,b]` | Adds `lifeos_category` and `lifeos_check` columns to a bank CSV. Fully local: keyword rules first, then local Qwen for the rest; refuses a non-local Ollama address, never overwrites, never writes inside a git repo, prints counts only. The first line must be a header (it decides the delimiter; it is never printed in an error). Rows the model could not place (it answered `other`, or its answer was wordy or outside the list) say `yes` in `lifeos_check`; rows placed by the keyword rules never do | Your spending sorted without bank data touching any cloud or chat |
| `lifeos mcp` | Runs a local MCP server (standard library only) with 16 tools for tasks, context, guarded model execution, reviews, learning loops, routing, Cockpit export, exams, bake-offs and showcase drafts. Writes stay inside the configured data repository | Chat apps use one consistent, auditable interface without copy and paste |
| `lifeos guard [files] / --staged` | Blocks validated IBANs/cards, contextual ID numbers, known key formats, private keys and assigned secrets; warns on emails and phone numbers. `--staged` scans the staged version; UTF-16 and legacy text are scanned | Catches high-confidence leaks before a commit; it is a backstop, not a complete classifier |
| `lifeos verify [--anchor HASH] [--json]` | Proves `logs/runs.jsonl` was not edited, deleted from the middle or reordered: every new record carries the SHA-256 of the line before it. Prints a head hash; save it outside the file and later pass it as `--anchor` to prove the last record and the tail were not cut or rewritten. Records from before the chain are counted as older, not as errors | Rule 1 (proof) made mechanical: the audit trail cannot be changed quietly |
| `lifeos replay <run-id> [--json]` | Rebuilds an `ask` run's context from today's files and compares it with the recorded hash. New run records keep a SHA-256 per context file (never the content) and the task length at that moment, so appended answers do not matter. Identical = the model saw exactly this input; otherwise it names the file that changed. Older runs and review runs are reported as not replayable | Proves which input produced which answer without storing the input |
| `lifeos doctor [--tools] [--live] [--smoke] [--only a,b]` | Checks the data repo; fails when the always-loaded core is over 2000 tokens or a file is too long; `--tools` checks binary availability; `--live` probes local Ollama model tags (`/api/tags`) and CLI `--version` execution; `--smoke` sends one tiny message per seat (`--only grok,claude` limits it), prints why a seat failed (redacted, one line), skips seats that are resting, and when a seat reports a usage limit saves a `smoke` record so `lifeos seats` and `delegate` rest it until the reset (a smoke record never counts as spend; a resting seat is not a fault) | Keeps the core small and distinguishes binary availability from live provider health |
| `lifeos lab {check,pack,score} <card> ...` | Offline Prompt Lab runner: `check` validates a prompt card and prints its `prompt` and `tests` hashes; `pack` prints the prompt and five test inputs (or `--filled` prompts, or `--results FILE`); `score` grades a results file offline and logs one proof row in `logs/proofs.csv` | Deterministic prompt testing with zero personal token draw and strict work/personal separation (rule 9) |

The `Delegation:` line of `lifeos week` judges models by numbers: it counts this week's `lifeos ask` ledger lines (`delegate` and `mcp` write them too) per model, most used first, and how many of those answers the free check flagged; the ledger keeps only that count, never the answer or the flag texts.

`LIFEOS_TIMEOUT=<seconds>` (1 to 3600) shortens the per-call timeout, for the live check in `docs/LIVE-CHECK.md`.

Two options go before the command name: `--home <path>` picks the data repo (default: `LIFEOS_HOME`, else the current folder, which must hold `now.md`); `--version` prints the version.

Eight portable skills (open Agent Skills format, read by Claude, Codex and Gemini) live in `skills/`: `lifeos-task`, `weekly-review`, `decision-memo`, `usage-handoff`, `work-prompt`, `german-tech-reader`, `iwa-demo-check` and `system-health`.

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

On this Windows laptop, double-click `scripts/open-learning-cockpit.cmd` to start the live Study Atelier and open `http://127.0.0.1:8765/#learning`. Keep its terminal window open; `Ctrl+C` stops the server.

Private patterns that must never be committed (your street, your phone number) go in `~/.lifeos/private-patterns.txt`, one regular expression per line, outside every repo. Mark a false alarm with `lifeos-guard: allow` on that line.

## Security boundaries

- `ollama` and `qwen` refuse any `OLLAMA_HOST` that is not `localhost`, `127.0.0.1` or `::1`.
- The allow marker works only for reviewed file scans; outbound context and model answers cannot exempt themselves.
- The guard cannot reliably recognize natural-language health, tenant or employer information. Those remain policy rules: do not put them in a task or context pack.
- The execution gate conservatively detects recognizable health, banking, identity-document, tenant, tax and salary context in task facts. `ask` and `review` refuse remote providers for those tasks and require local Qwen/Ollama; the byte-pattern guard remains the final credential/identifier backstop.
- The live Cockpit accepts writes only from localhost pages holding its per-process token, validates the Host and content type, limits request size, emits restrictive browser headers, and returns generic errors. Static export has no write capability or external font/network dependency.
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
| v0.3 | Gate 2, 17 Jan 2027 | Prompt Lab runner (`lifeos lab check/pack/score`): prompt cards validated, packed for the work console and scored offline with proof logging; repo goes public |
| v0.4 | Gate 3, 28 Mar 2027 | Dashboard from the logs; GitHub Actions pipeline |
| v0.5 | Jun 2027 | Model router (LangGraph, LiteLLM budgets) evaluated on 50 real tasks |
| v1.0 | Nov 2027 | Hardening, evaluation report and public case study |

## Rules for this repo

Standard library only unless a pull request explains why. Tests first. No personal data, ever. Work on a branch; the owner merges.

Licence: MIT (see `LICENSE`).

## Chat apps without copy and paste (`lifeos mcp`)

Claude Desktop: add this to `claude_desktop_config.json` under `mcpServers`, then restart the app.
Use your own path for LIFEOS_HOME.

```json
"lifeos": {"command": "lifeos", "args": ["mcp"], "env": {"LIFEOS_HOME": "C:\\Users\\you\\lifeos"}}
```

Claude Code: `claude mcp add -s user lifeos -e LIFEOS_HOME=<path> -- lifeos mcp` (or `python -P -m lifeos.cli mcp` on Python 3.11+; using `lifeos` or `-P` keeps a `~/lifeos` data repo folder from shadowing the `lifeos` package when the app starts in `~`).
Other MCP apps (Codex, agy) use the same program and `LIFEOS_HOME` environment variable.
`lifeos_ask` can take minutes; some apps stop waiting after about a minute. Screenshots stay in the chat.

## Claude as the lead

Register `lifeos mcp` in Claude (Desktop or Code). The server tells Claude its role: for work that fits another model it calls `lifeos_delegate`, reads the answer that comes back in the same chat, checks it against rules.md and writes the decision into the task file. You only talk to Claude.

Local models run through one Ollama installation. The laptop-sized default is `qwen3.5:4b` for `lifeos ask qwen`; the optional model kit adds `deepseek-r1:1.5b` for reasoning and `qwen2.5-coder:3b` for code. Install the audited set from PowerShell with `scripts/install-local-models.ps1 -InstallRuntime`, then run a task with `scripts/use-local-model.ps1 -Role tutor|reasoner|coder -Task T-...`. Override Qwen with `LIFEOS_QWEN_MODEL` or the generic Ollama adapter with `LIFEOS_OLLAMA_MODEL`. Both use the loopback-only `OLLAMA_HOST` (default `http://localhost:11434`); reasoning blocks (`<think>`) are stripped from local answers.

