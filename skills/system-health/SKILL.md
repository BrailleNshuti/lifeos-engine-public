---
name: system-health
description: Run the first-Sunday Monthly System Health & Kaizen check (Section 10.3), audit 4-week trials in system/changes.md, and propose one improvement PR.
---
# Monthly System Health & Kaizen Loop (First Sunday)
1. Run `lifeos kaizen --draft` (or `lifeos kaizen --month YYYY-MM --draft`) to compute the 28-day metrics from `logs/runs.jsonl`, `logs/ledger.csv`, `logs/proofs.csv`, `logs/hours.csv`, `logs/health.csv`, and `system/changes.md` into `reviews/YYYY-MM.md`.
2. Verify that all five questions in `reviews/YYYY-MM.md` cite measured numbers from the logs:
   - Routing waste (failed/blocked runs, token usage, flagged answers per model).
   - Repeated manual tasks to turn into Tier-0 scripts or templates.
   - The single rule, template, or automation change with the highest expected return.
   - Weakest scoreboard area and one small 4-week experiment.
   - Unused or heavy system parts to pause, plus `KEEP or REVERT` verdicts for any trial in `system/changes.md` that has reached 28 days.
3. Respect the guardrails (Section 10.4): never modify L3 rules, data classes, budget caps, or `main` directly; propose at most one trial change on a branch (`claude/kaizen-YYYY-MM-...` or `gemini/kaizen-YYYY-MM-...`) with a clear baseline metric and review date (+28 days).
