# Daily use: five commands and what to do when they fail

Written from the first week of real use (2026-11-26). Everything here ran on a real task.

## Start here every morning

Run `lifeos next`. It names the one thing to do now and the exact command: damaged files first, then an overdue task, an answer you have not rated, a waiting item that is due, the next open task. Close a finished task with `lifeos task close <id> --proof "..."` and keep the waiting list with `lifeos waiting add|list|done`.

## The loop

1. **Make the task.** `lifeos task new --level L1 "one sentence goal"`, then open the file and write the `done_when` line yourself:
   what the answer must contain so you can tell it worked (a number, a URL, a date). Put the facts the seat needs under
   *Context*. A seat sees only the task and the rules, not your files.
2. **See the cost first.** `lifeos ask <seat> <task> --dry-run` prints the pack and the token cost and sends nothing.
3. **Ask.** `lifeos ask <seat> <task>`. Read the `CHECK` line it prints: it is free and says where to look first (a missing URL
   or date your `done_when` asked for, a seat that only promised to save, a quote that is not in your context).
4. **Check by hand.** Open every URL, grep every quoted line, run every command the answer relies on. The `CHECK` line does not
   prove an answer right.
5. **Rate.** `lifeos rate <task> <seat> <1-5> --note "what was wrong or right"`. Add a `kind:` line to the task file if the
   router would file it under the wrong kind of work.

## Which seat

| Job | Seat | Why |
|---|---|---|
| Review code or a document, find bugs | codex, gemini | rated 4 for review work in week one |
| Plans, writing, comparing options | claude | rated 4 |
| Public live facts from open pages | grok | public questions only; shop and price sites block it |
| Small private jobs, sorting | qwen, ollama | stay on the laptop; slow on this CPU until the RAM upgrade |
| Anything with IDs, bank, passwords, health, tenants | local seats only | never a cloud seat |

## When something fails

| What you see | Meaning | Do this |
|---|---|---|
| `grok failed: Error: max turns reached` | the seat ran out of its 3 turns | name the pages to fetch in *Context*, at most two |
| Grok answer says "I'll save..." with no content | the seat has no write tool | rerun; the engine now tells it to answer in the reply |
| `ollama did not answer within 240 s` | local model too slow | use `lifeos delegate <task>` instead of `ask`: it tries the next seat in the chain by itself (never a cloud seat for private tasks); or set `LIFEOS_TIMEOUT` |
| `budget governor` holds the call | weekly budget or call count near its limit | wait for the reset, or `--force` once if it matters |
| `BLOCKED` by the guard | the text looks like an ID, key or card | remove it or use a local seat |
| CI `proof` or `trailers` fails on a PR | a test failed, or a Co-Authored-By line slipped in | read the log, fix, push again; never add trailers |
| `os.replace failed` on Windows | the write flake (unproven cause) | do not retry by hand; keep both files, run `lifeos doctor`, tell Claude |

## Weekly

- Sunday: `lifeos earn`, `lifeos mistakes`, `lifeos stale`, then the weekly-review skill.
- First Sunday of the month: the no-ai-exam and system-health skills.
- Refresh the dashboard: `lifeos dash-export --out <folder>` and give the seven files to Claude to upload.
