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
lifeos doctor --tools --smoke
grok inspect --json           # confirm no LifeOS MCP server is configured for Grok
```

Close the shell afterwards; nothing is changed outside it.
