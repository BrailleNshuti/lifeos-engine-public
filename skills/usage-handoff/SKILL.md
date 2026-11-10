---
name: usage-handoff
description: Protect long work from usage limits. Use before any big task, when a session has run long, or when the 5-hour or weekly usage is high.
---
# Usage hand-off
1. Before a big task, check the usage (`/usage` in Claude Code, or ask the user). Start big tasks only below 60 % of the 5-hour window and 80 % of the weekly limit.
2. Work in small steps and save state as you go: done, next, file paths (in the task file or a NOTES file).
3. At about 75 % of the window, or when usage is unknown and the session has run long: finish the current step, write the hand-off, and schedule the continuation after the next reset if the tools allow it.
4. Keep the hand-off under 15 lines so the next session starts cheap.
5. Never start a large new step right before a limit.
