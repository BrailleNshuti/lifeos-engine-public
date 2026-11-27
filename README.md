# LifeOS Engine

The machinery of a personal AI operating system: one shared memory that Claude, Codex, ChatGPT and Grok all work from, plus the tools that keep it honest, cheap and private.

The engine is code only. Your life lives in a separate **private data repo** (`lifeos`): rules, profile, current week, task files, logs and reviews. The engine reads it through `LIFEOS_HOME`; nothing personal is ever stored here, and everything in `examples/` is made up.

## See it in 60 seconds

```
pip install -e .
lifeos demo
```

`lifeos demo` runs on made-up data, with no account, model or network, and checks each claim in code: the guard refuses a fake secret, a blind panel finds two models disagreeing, an edited ledger record is caught, replay proves which input a run saw, and a removed last record is caught by the saved head hash.

| Check it yourself | Command |
|---|---|
| Guard score on generated fake identifiers | `lifeos canary` |
| Whole proof in one file | `lifeos prove --out proof.md` |
| Secrets anywhere in the git history | `lifeos history-scan` |
| Facts about the engine, one page | `lifeos numbers --html numbers.html` |

Why it is built this way, and what each choice costs: [docs/DESIGN.md](docs/DESIGN.md). What it promises and what it does not, with the test behind each promise: [docs/SECURITY.md](docs/SECURITY.md). File formats: [docs/LOGS.md](docs/LOGS.md). Every pull request also runs `lifeos prove` and `lifeos demo` in CI and attaches the proof as a build artifact.

## What it does

| Command | What it does | Why it matters |
|---|---|---|
| `lifeos task block ID --reason TEXT` | Pauses a task on purpose: status blocked and the reason as a dated update. Refuses a done task, an empty reason or private text | A paused project stays visible and is not suggested by `next` |
| `lifeos task close ID --proof TEXT [--result TEXT]` | Marks a task done: the proof goes under `## Proof` and an optional result above it, in one locked atomic write. Refuses without a checkable proof (link, file, test or PR number), with a TODO finish line, with private data, or when already done | Closing a task the way rule 1 asks, without a hand-written script |
| `lifeos task new "<one sentence>" [--route R] [--level L2] [--due 2026-11-30]` | Creates `tasks/T-YYMMDD-name.md` from the hand-off template (route defaults to `Claude Code -> Codex review`, level to `L2`, one of L0 to L3); you only write the done-when line | Hand-offs between models in seconds, never overwrites a file |
| `lifeos task list [--status doing]` | Lists task files with status and due date | One look at open work |
| `lifeos week [--week 2026-W47] [--draft] [--redteam] [--json]` | Proofs, net time saved, logged hours (`hours.csv`) and daily health averages (`health.csv`) from the logs, plus a `Delegation:` line with model calls and flagged answers; `--draft` creates `reviews/<week>.md` without overwriting; `--redteam` prints a facts-only Red-Team pack | Numbers come from data, never from a model's guess |
| `lifeos log {proof,ledger,health,hours} ... [--date YYYY-MM-DD]` | Appends one validated, guard-checked, UTF-8/LF row to `logs/proofs.csv`, `logs/ledger.csv`, `logs/health.csv` or `logs/hours.csv` under the store lock; refuses duplicate consecutive rows, out-of-range numbers and privacy guard hits | Fast, corruption-proof daily logging without manual CSV editing |
| `lifeos runs [--status S] [--model M] [--task ID] [--limit N] [--json]` | Inspects the execution audit trail in `logs/runs.jsonl`: filters by status (`ok`, `failed`, `timeout`, `blocked`, `tool_missing`, `partial`), model or task prefix, and summarizes status counts, average duration and token usage | Immediate visibility into every model call, failure and blind review without opening raw JSONL |
| `lifeos kaizen [--month YYYY-MM] [--draft] [--json]` | Monthly System Health & Kaizen loop: analyzes the last 28 days of logs and `system/changes.md` to answer the 5 System Health questions and optionally draft `reviews/<YYYY-MM>.md` | Self-improving rules backed by measured 4-week trials |
| `lifeos route <task_or_text> [--tier T] [--full] [--json]` | Evaluates all 6 routing questions (confidential-work-data check, Tier-0 script check, 5-tier data policy, model matrix, L0–L3 blind review requirement, and weekly token/call budget guard) | Deterministic routing decisions before spending tokens |
| `lifeos cockpit [--export FILE] [--serve] [--port 8765]` | Exports or serves the private **Study Atelier** (`#learning`, `#study`, `#practice`, `#exam`, `#mastery`) with a focus contract, source library, verified recall queue, exam forge, recovery mode and evidence shelf | Makes learning the default experience; project and agent machinery stay secondary. Your own focus line, bets horizon, exam targets and log-area labels (valid ids: `study`, `lab`, `work`, `german`; the defaults show the first three) come from an optional `cockpit.json` in the data home (see `examples/demo-home/cockpit.json`); without it the cockpit shows neutral defaults |
| `lifeos study {sources,import,bank,verify,attempt,exam}` | Imports guarded notes, generates source-grounded question candidates, records human verification and retrieval intervals, and freezes printable mock papers with separate answer keys | Turns notes into trustworthy practice without sending study content to a model or hiding fabricated answers in the static Cockpit |
| `lifeos context [TASK] [--budget 6000] [--explain]` | Prints rules, the task, now and me in priority order, trimmed to a token budget; `--explain` shows which files were included, trimmed or excluded, their token cost and SHA-256 fingerprint | Paste once, pay little; shows the token cost and provenance before you send |
| `lifeos ask <model> <task> [--budget N] [--full] [--run-id ID] [--dry-run] [--force]` | Generates a pre-execution `run_id`, guards the context pack, sends it to that model (codex, claude, ollama, qwen, or gemini through Antigravity `agy`), and commits the task result, ledger row and run record (`logs/runs.jsonl`) in one locked, journal-recoverable transaction. Also logs blocked, failed, timed-out and missing-tool runs with secret redaction | Work moves between models with retry idempotency, crash recovery and a complete audit trail. Notes listed under `## Context` (`.md` or `.txt` inside the data repository, up to four, never under `logs/` or `.git`, never outside it) are attached to the pack and shown by `--dry-run`. The budget governor checks the week's cloud token and call caps, the seat's share and any usage-limit rest before sending, prints one line, and holds the call (exit 4, nothing sent) unless `--force`; local seats are never held |
| `lifeos delegate <task> [--model M] [--budget N] [--full] [--dry-run]` | Picks the open seat from one table (`lifeos/seats.py`): Qwen for private, sensitive and small local jobs; Claude writes code, plans and decisions; Codex tests, reviews, German and exams; Gemini does long reading and research; the locked Grok seat answers live facts (prices, news, today) with a source and a date (headless, JSON out, empty temp folder, no plan mode or subagents, at most 3 agent turns, unapproved tools refused with `dontAsk`, prompt passed in a private temp file; never selected for sensitive work, never with `--full`). Every seat gets the same prompt: one instruction plus one context pack. One cloud budget: a seat's limit is the lower of its 7-day share (Claude 40k, Codex 40k, Gemini 30k, Grok 20k) and what the weekly cap (120k tokens, 80 calls for all cloud seats) has left; a seat at its limit, or at its 24-call cap, is skipped. A usage-limit message rests the seat until the time it names: converted when it names a zone, read as UTC and flagged when it does not, a relative wait ("Resets in 78h40m32s", "try again in 45 minutes") is counted from the failure; 12 h when it names no time or one before the failure; capped at 8 days. A missing tool or failed call is replaced by the next open seat and the reason is written under `## Route` (not sent to the next model). A local or sensitive task never moves to a cloud seat. Flags: `degraded` when a small local model answered where a cloud seat was meant to; `check pending` when the checking seat is resting, missing, or is the one that wrote it. Prints the answer plus a free CHECK line | One command instead of choosing a model by hand; one provider running out does not stop the task, and nothing is skipped in silence |
| `lifeos seats [--json]` | One row per seat: 7-day tokens against its one limit, resting reason, replacement seat | See at a glance who is open and who takes over |
| `lifeos review <task> [--reviewers codex,claude] [--repo PATH] [--commit SHA] [--run-id ID] [--budget N] [--dry-run]` | Runs an independent blind review (rule 7) across multiple models on the same pre-committed facts-only pack (stripping prior `## Result` blocks). With `--repo`, embeds the exact 40-char commit SHA, branch, tracked file list and unified diff into the pack and runs reviewer CLIs inside an isolated detached `git worktree` at that commit; records both child `review` records and the parent `review_group` record (including partial/failed states) in `logs/runs.jsonl` | Multi-model verification on the exact repository commit without echo-chamber bias |
| `lifeos sort-csv <file> [--out F] [--column C] [--categories a,b]` | Adds `lifeos_category` and `lifeos_check` columns to a bank CSV. Fully local: keyword rules first, then local Qwen for the rest; refuses a non-local Ollama address, never overwrites, never writes inside a git repo, prints counts only. The first line must be a header (it decides the delimiter; it is never printed in an error). Rows the model could not place (it answered `other`, or its answer was wordy or outside the list) say `yes` in `lifeos_check`; rows placed by the keyword rules never do | Your spending sorted without bank data touching any cloud or chat |
| `lifeos mcp` | Runs a local MCP server (standard library only) with 16 tools for tasks, context, guarded model execution, reviews, learning loops, routing, Cockpit export, exams, bake-offs and showcase drafts. Writes stay inside the configured data repository | Chat apps use one consistent, auditable interface without copy and paste |
| `lifeos guard [files] / --staged` | Blocks validated IBANs/cards, contextual ID numbers, labelled tax and social security numbers, stated PINs, known key formats, web tokens, private keys and assigned secrets; warns on emails and phone numbers. `--staged` scans the staged version; UTF-16 and legacy text are scanned | Catches high-confidence leaks before a commit; it is a backstop, not a complete classifier |
| `lifeos verify [--anchor HASH] [--seal] [--json]` | Proves `logs/runs.jsonl` was not edited, deleted from the middle or reordered: every new record carries the SHA-256 of the line before it. Prints a head hash; save it outside the file and later pass it as `--anchor` to prove the last record and the tail were not cut or rewritten. Records from before the chain are counted as older, not as errors; `--seal` (once) pins them in `logs/runs.seal.json` so a later rewrite of them is caught | Rule 1 (proof) made mechanical: the audit trail cannot be changed quietly |
| `lifeos replay <run-id> [--json]` | Rebuilds an `ask` run's context from today's files and compares it with the recorded hash. New run records keep a SHA-256 per context file (never the content) and the task length at that moment, so appended answers do not matter. Identical = the model saw exactly this input; otherwise it names the file that changed. Older runs and review runs are reported as not replayable | Proves which input produced which answer without storing the input |
| `lifeos canary [--json]` | Guard score and leak proof. Generates made-up, checksum-valid IBANs and card numbers in many layouts (seeded, identical every run) plus tokens and an ID line, and reports how many the guard blocks and whether ordinary text is wrongly flagged. Then plants one of each kind in a throwaway task and proves `ask` stops before sending: no model is called and nothing reaches `logs/runs.jsonl`. Exit 1 on any miss | A number anyone can reproduce: the guard blocks N of N generated layouts (run it) |
| `lifeos panel <task> --models a,b[,c] [--json] [--full]` | Asks two to four models the same task, each separately with the identical context pack (no model sees another's answer), then compares the answers claim by claim without another model call and appends a report to the task: agreed by all, majority, conflicts (same point, different numbers or opposite wording), only one model. A model that fails is listed, not fatal | Turns "ask several models" into blind, pre-committed review (rule 7): disagreement is where to look first, agreement is not evidence |
| `lifeos debate {start,next,record,run,score}` | Blind debate, three rounds, two to four seats. Each seat answers alone from one identical pack; then sees the OTHER answers relabeled A/B/C in a seeded order (names and 64-character hashes scrubbed) and raises at most 3 objections per answer (target, claim, evidence, kind, optional settle test); then sees only the objections against its own answer, without authors, and concedes, rebuts or revises. `score` is rules, no model: an objection without checkable evidence is an opinion and does not count; every claim gets SURVIVED (nobody showed otherwise, not proof), FELL (conceded or unanswered; a rebuttal or revision without evidence counts as conceding) or OPEN (evidence on both sides; prints the settle test). Agreement is logged, never used. `run` is a dry run unless `--run` and skips a seat that is down instead of replacing it. Every answer, the question file and the round 1 pack are hashed into the chained ledger; a changed one is refused. `score --reveal` adds a per-seat scorecard. Protocol: [docs/DEBATE.md](docs/DEBATE.md) | Only ideas that survive on evidence count; agreeing models are not evidence (rule 6) |
| `lifeos rate <task> <model> <1-5> [--note ..]`, `lifeos learn [--json]`, `lifeos delegate <task> --learned`, `lifeos rate --walk` | `rate` stores your score in `logs/ratings.csv` under the kind of work the router recognised (or the task file's own `kind:` line, which wins), notes when the route names a review that never ran, and ends with one `router:` line saying whether the evidence now favours another seat; `learn` shows mean and count per kind and model; `delegate --learned` picks a different model only when it has 3+ ratings and beats the default by a full point, otherwise the default stands (a note with private data is refused) | The router improves from your outcomes, not from a model's opinion of itself (rules 2 and 11) |
| `lifeos unrate TASK [MODEL]` | Removes the last rating of a task (of one model if named), under the store lock, when a rating was a mistake. Exit 1 if there is none | A wrong score no longer needs a hand edit of `logs/ratings.csv`. `rate` also warns when a score of 2 or less has no note |
| `lifeos predict "<claim>" --p N`, `lifeos resolve <P-id> yes\|no`, `lifeos calibration [--json]` | Write down what you expect and how sure you are (1-99 %) before you know; record what happened; get the Brier score and, per confidence band, what you said against what happened (`logs/predictions.csv`, append-only; claims with private data are refused) | Shows whether your "I'm sure" holds up, with numbers (rules 2 and 6) |
| `lifeos mistakes [--count N] [--json]`, `lifeos vocab add \| quiz [--reveal] \| answer` | `mistakes` lists the verified study questions you missed most and have not fixed yet (prompts only); `vocab` keeps your own German words with an example from your own day and a 1/3/7/14-day box schedule (`logs/vocab.csv`, local, no model call, private data refused) | Practice follows your real errors and your real words, not a fixed list |
| `lifeos numbers [--out FILE] [--html FILE] [--json]` | Builds an "Engine in numbers" page: modules, lines, tests, commands, the guard score on generated fake identifiers, ledger chain status and counts of ratings, predictions and own words. Counts only, no task text or paths | A page anyone can check by running the same command |
| `lifeos dash-export --out DIR` | Writes seven JSON files for a dashboard, all or none (numbers, runs by seat, ratings with notes, tasks, what left per cloud seat, seat speed, and a waiting list you keep by hand in `waiting.json`); no model call, nothing leaves the laptop | Refreshing a dashboard is one command, not hand editing. The files hold task goals and rating notes: load them only into a page only you can open |
| `lifeos waiting add "..." [--who W] [--when D]` / `list` / `done N` | The waiting list (`waiting.json`) without editing JSON: add what waits, show it numbered, remove one. Locked and atomic, the text is guard-checked, a damaged file is never overwritten | Keeping the list that `today` and the cockpit show true, in one line instead of a hand edit |
| `lifeos next` | The one thing to do now with the exact command, in a fixed order: damaged files, overdue task, unrated answer, waiting item due within three days, next open task. Read only, no model call | Starting the day with one decision instead of a list |
| `lifeos selfcheck` | One pass over your own files: the run-ledger chain, every task file (as `lint`), the ratings log row by row and the waiting list. Names each problem with its file and line, exits 1 on damage, never repairs anything | Knowing your data is sound before you trust a report built from it |
| `lifeos egress [--days N]` | What left this laptop: per cloud seat the calls sent, failed and blocked by the guard, the tokens and the last call, from the run ledger. Counts only, never any prompt or answer text; local models never appear; a WARNING line when a seat passed its weekly token share | The answer to "what did I send to the cloud this month" without opening a log |
| `lifeos help-me` | Prints the daily loop (task, dry run, ask, check, rate, weekly review) with the exact commands | The five steps on one screen, the same as `docs/DAILY.md` |
| `lifeos commands [--out FILE]` | Prints, or writes to a file, the list of every command with its help line and options, generated from the parser (`docs/COMMANDS.md`); a test fails when the checked-in page is stale | The command list cannot drift from the code. `ask --failover` lets the next seat answer when the first fails, like `delegate` |
| `lifeos sunday [--save]` | The numbers for the weekly review on one page: what earned its place, seat speed, this week's ratings with their notes, stale items and open mistakes. No model call, writes nothing | One command before the weekly-review skill instead of five |
| `lifeos verify-quotes TASK` | Checks that every quoted line (25 characters or more) in the latest answer of a task is really in the task's context; prints real over total and the missing lines; exit 1 if any is missing. No model call | The check I did by hand with grep, now one command. A seat that fetched its own pages quotes text that is not in the context: the command says so |
| `lifeos prove [--out FILE] [--skip-tests]` | Runs the tests, the guard score, the outbound stop and the ledger chain, then writes one dated proof file with the numbers page; exit 1 if anything fails. No model call | Rule 1 in one command: a file you can link |
| `lifeos history-scan [--max-commits N]` | Scans every commit on every branch for class C data (added lines only, masked output); exit 1 if found; reviewed exceptions go in `.lifeos-history-allow` (`<12-char commit> <path>  # reason`, exact match only) | A secret deleted later is still public in a public repo's history |
| `lifeos hook install [--force]` | Installs a pre-commit hook that runs `lifeos guard --staged`; never overwrites a different hook without `--force` | The guard runs without you remembering it |
| `lifeos digest [--json]` | Sunday review in numbers: per part, uses this week, last use and a verdict; no use for 14 days says pause or remove | Rule 10: every part must earn its place |
| `lifeos demo [--json]` | A 60-second tour on made-up data in a throwaway folder: the guard refuses a fake key, a blind panel finds a conflict, an edited ledger record is caught, replay proves an input, a cut tail is caught by the anchor. Each step is checked by code. No account, model or network | Shows the promises working instead of describing them |
| `lifeos savings [--json]` | Tokens the context packs sent to cloud models against what pasting every note each time would have cost, from your own ledger (an estimate, and it says so) | A measured claim about token cost |
| `lifeos experiment start "<change>" --metric M [--days N]` / `end ID` / `list` | Rule 11 as a tool: one tested change at a time. `start` records the change and the baseline (metrics: minutes_saved, proofs, failed_rate, avg_tokens, rating); `end` after the trial days says keep (at least 5 % better), revert, or inconclusive (fewer than 3 data points). Only one experiment runs at a time; the log only grows | An unproven rule change never stays by default |
| `lifeos pipeline NAME [--run]` | Runs a saved flow from `pipelines/NAME.json` (a list of lifeos commands). Dry run by default; `--run` executes. A failing step stops the rest unless its gate is `continue`. No nesting; no private data in arguments | Repeatable routines with a stop gate |
| `lifeos decide add "<title>" --why "..." [--revisit DATE] [--predict "claim" --p N]` / `list` / `due` | Short decision records in `decisions/`. A revisit date puts the decision on the `due` list when it comes; `--predict` files a calibrated prediction (see `predict`). Never overwrites; private data refused | Decisions get judged against numbers later |
| `lifeos backup --out DIR` / `--check DIR` / `--restore DIR` | Copies `logs/` into `DIR/lifeos-backup-YYYYMMDD/` with a MANIFEST of SHA-256 hashes and the run-ledger head; `--restore` puts a checked backup back (the logs it replaces are moved aside to `logs.before-restore-<time>`, never deleted); `--check` finds changed, missing or extra files. Never overwrites, never writes inside your home, uploads nothing | Logs are the part you cannot rebuild |
| `lifeos redact FILE... --out DIR` | Writes copies where every line the guard flags (keys, IBAN, cards, e-mails, phones, your private patterns) becomes `[redacted: kind]`. Same line count, the secret is removed not masked, the result re-scans clean. Originals untouched, copies never overwritten | Share a log without leaking a line |
| `lifeos release [--repo PATH]` | Read-only release plan: checks that pyproject and `__version__` agree, counts the `[Unreleased]` entries, proposes a bump (new command means minor, fixes only means patch) and prints draft notes. Edits, tags and pushes nothing; the version and tag are yours to decide | Release facts without the risk |
| `lifeos earn [--days N]` | Rule 10 as a table: for each part with a log (ask, debate, rate, predict, vocab, experiment, decide, ledger, proofs, tasks) the uses in the last N days, the last use, and "earns its place" or "pause or remove?"; then a seat speed table (calls that answered, failures, median and worst seconds per seat). Removes nothing; a number for the Sunday review | Parts must earn their place |
| `lifeos bakeoff [--quarter YYYY-Qn] [--task-type T] [--model-a A --model-b B] [--scores JSON] [--draft]` | Quarterly blind comparison of two models on one kind of task: writes the sealed plan first, unseals the winner only when scores are given | Pick models by evidence, not mood |
| `lifeos exam [--month YYYY-MM] [--module M] [--draft] [--score-skill S --score-pct N]` | Monthly no-AI exam draft for a study module, and records a graded result against a skill | Rule 3: attempt first, measure it |
| `lifeos showcase [--week YYYY-Www] [--draft]` | Weekly post draft built from the week's numbers, guarded for private data; writes `reviews/post-<week>.md` | Evidence you can show |
| `lifeos today` | One screen for the day from files you keep: the next task (overdue first), other open tasks, decisions to revisit, words due, open predictions, the running experiment. Read-only, no model call | Start the day with the hard thing named |
| `lifeos lint` | Checks every task file: id matches the file name, goal, a real `done_when` (not the TODO placeholder), level L0-L3, status, due date, and proof (a link, file or test) on done tasks (rule 1). Read-only; exit 1 on any problem | Bad hand-offs caught early |
| `lifeos stale [--days N]` | Lists what has sat too long: open tasks and unresolved predictions older than N days (default 14) and decisions past their revisit date. Read-only; closes nothing for you | Open loops get finished or dropped on purpose |
| `lifeos completion powershell\|bash` | Prints a tab-completion script built from the real argument parser, so it never lists a missing command or misses a new one. PowerShell: add the output to your `$PROFILE`. Prints only; installs nothing | Tab-complete every command |
| `lifeos schema [--write FILE] [--check FILE]` | Prints (or writes, or checks) the format of every log and file the engine writes, generated from the code's own header constants; committed as `docs/LOGS.md` with a drift test | Logs are plain text you can read and back up |
| `lifeos timeline [--weeks N]` | Proofs and minutes saved per ISO week, oldest first, with a bar; empty weeks are shown because a gap is information. Read-only | See the rhythm, not just the total |
| `lifeos export --out FILE` | One evidence page for a CV or portfolio: recent proofs, minutes saved, ledger head and chain status, calibration, weekly rhythm. Every line the guard flags is replaced, so the page is safe to share. Never overwrites; sends nothing | Evidence you can hand to anyone |
| `lifeos selftest [--example PATH]` | Runs 44 steps (demo, canary, prove, context, route, ask and delegate dry runs, guard, predict, vocab, rate, verify, savings, numbers, today, earn, lint, stale, timeline, decide, experiment, export, redact, backup, schema, pipeline, a debate round trip with no model, and more) against a throwaway copy of the demo home and prints PASS or FAIL for each; exit 1 on any failure. Never touches your notes, calls no model | One command to know the install works |
| `lifeos arch [--write FILE] [--check FILE]` | Draws the module graph (Mermaid) from the real imports; `docs/ARCHITECTURE-GRAPH.md` is generated by it and a test fails when that file no longer matches the code (`--check` exits 1 if stale) | Architecture documentation that cannot go stale |
| `lifeos doctor [--tools] [--live] [--smoke] [--only a,b]` | Checks the data repo; fails when the always-loaded core is over 2000 tokens or a file is too long; `--tools` checks binary availability; `--live` probes local Ollama model tags (`/api/tags`) and CLI `--version` execution; `--smoke` sends one tiny message per seat (`--only grok,claude` limits it), prints why a seat failed (redacted, one line), skips seats that are resting, and when a seat reports a usage limit saves a `smoke` record so `lifeos seats` and `delegate` rest it until the reset (a smoke record never counts as spend; a resting seat is not a fault) | Keeps the core small and distinguishes binary availability from live provider health |
| `lifeos lab {check,pack,score} <card> ...` | Offline Prompt Lab runner: `check` validates a prompt card and prints its `prompt` and `tests` hashes; `pack` prints the prompt and five test inputs (or `--filled` prompts, or `--results FILE`); `score` grades a results file offline and logs one proof row in `logs/proofs.csv` | Deterministic prompt testing with zero personal token draw and strict work/personal separation (rule 9) |

The `Delegation:` line of `lifeos week` judges models by numbers: it counts this week's `lifeos ask` ledger lines (`delegate` and `mcp` write them too) per model, most used first, and how many of those answers the free check flagged; the ledger keeps only that count, never the answer or the flag texts.

`LIFEOS_TIMEOUT=<seconds>` (1 to 3600) shortens the per-call timeout, for the live check in `docs/LIVE-CHECK.md`.

Two options go before the command name: `--home <path>` picks the data repo (default: `LIFEOS_HOME`, else the current folder, which must hold `now.md`); `--version` prints the version.

Eight portable skills (open Agent Skills format, read by Claude, Codex and Gemini) live in `skills/`: `lifeos-task`, `weekly-review`, `decision-memo`, `usage-handoff`, `work-prompt`, `german-tech-reader`, `demo-readiness-check` and `system-health`.

## Quick start (Windows PowerShell or any shell)

```
pip install -e .                      # from this folder; standard library only
$env:LIFEOS_HOME = "C:\path\to\lifeos" # bash: export LIFEOS_HOME=~/lifeos
lifeos doctor
lifeos task new "Draft the demo checklist"
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
| v0.2 | 6 Dec 2026 | Scoreboard from all logs, context packs per tool, the scheduled weekly review using these commands |
| v0.3 | 17 Jan 2027 | Prompt Lab runner (`lifeos lab check/pack/score`): prompt cards validated, packed for the work console and scored offline with proof logging; repo goes public |
| v0.4 | 28 Mar 2027 | Dashboard from the logs; GitHub Actions pipeline |
| v0.5 | Nov 2026 | `lifeos debate`: blind three-round debate scored by rules, with a per-seat scorecard; write-retry on Windows sharing violations; personal study targets and project names moved out of the public tree |
| v0.6 | Jun 2027 | Model router (LangGraph, LiteLLM budgets) evaluated on 50 real tasks |
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

