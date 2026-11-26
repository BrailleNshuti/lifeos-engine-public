# Live failover check

Proves that a failing seat is replaced by a real subprocess, not a mock. All data is made up (`examples/demo-home`).

## Recorded run (stand-in programs, 2026-11-17)

`codex` was a small script that prints a usage-limit message and exits 1; `claude` was a script that prints an answer. These are stand-ins for the real tools, not the providers.

```
$ lifeos --home demo delegate T-261116
claude: ... · codex failed (usage_limit: ... try again at Nov 18th, 2026 4:02 PM); fell back
$ lifeos --home demo delegate T-261116      # second call
claude: ... · skipped codex: usage limit until 2026-11-18 16:02 UTC (no timezone given, read as UTC)
codex calls: 1   claude calls: 2
```

Task file after the first call:

```
## Route · 2026-11-17
- codex usage_limit (R-...): codex failed: You've hit your usage limit. try again at Nov 18th, 2026 4:02 PM
- claude answered.
```

With a `codex` that sleeps and `LIFEOS_TIMEOUT=1`: `codex timeout ... timed out after 1 s.` then `claude answered.`

## Run it with the real tools (PowerShell)

```powershell
$env:LIFEOS_HOME = "C:\path\to\a-COPY-of-examples\demo-home"   # never your real data repo
$env:LIFEOS_TIMEOUT = "2"                                      # a 2 second timeout
# 1. hide Codex from this shell only
$env:PATH = ($env:PATH -split ';' | Where-Object { -not (Test-Path (Join-Path $_ 'codex*')) }) -join ';'
lifeos delegate T-261116      # expect: codex not available; fell back; Route note written
lifeos seats                  # expect: every seat listed, replacement column filled
# 2. smoke test Grok (needs the grok CLI): flags are unverified until this passes
lifeos doctor --smoke --only grok   # prints the reason if it fails; a usage limit rests the seat
grok inspect --json           # confirm no LifeOS MCP server is configured for Grok
```

Close the shell afterwards; nothing is changed outside it.

## Grok seat, live check (2026-11-26)

Grok CLI 1.0.77 on Windows. Every call ran with `LIFEOS_HOME` pointing at a throwaway copy of `examples/demo-home` and in an empty temp folder, so a tool that ran could only touch made-up data. n=1 per probe; none of these is a test suite.

| Check | Result |
|---|---|
| `lifeos doctor --smoke --only grok` | healthy (smoke ok) |
| `grok inspect --json` | lists an MCP server named `lifeos` (stdio), imported from the user's Claude config (`claudeJson`). The check above expects none. **Fails.** |
| Engine flags (`--no-plan --no-subagents --max-turns 3 --permission-mode dontAsk`), prompt "run `echo LIFEOS_PROOF_A`" | Grok ran it and quoted the output. A read-only shell command is **not** refused. |
| Same flags, prompt "call the MCP tool `lifeos_task_list`" | Grok began the call ("I'll look up the schema and call it"); the 3-turn limit ended the answer, so the result was not captured. The tool is reachable. |
| Same flags, prompt "create a file with a shell command" | The file was not created, and the answer ended without a verdict. Inconclusive: refused, or out of turns. |
| Same flags plus `--tools web_search`, shell prompt | "NO TOOLS": the shell tool was gone. |
| Same flags plus `--tools web_search`, MCP prompt | No output within 100 s. Inconclusive. |

What this means: the seat's description ("tools refused") is not true as built. `dontAsk` is not a lock: it let a read-only shell command run, and the MCP server is configured. An allowlist (`--tools`) removes the shell tool; whether it also stops the MCP server is not yet shown. Until the seat is fixed, send Grok public questions only, never a context pack.

Next, test first: the command line built by `ask_grok` must carry a tool allowlist, and a live probe must show that `lifeos_task_list` cannot be called. Candidate flags from `grok --help`: `--tools`, `--disallowed-tools`, `--deny`, `--sandbox`.
