---
name: iwa-demo-check
description: Verify the iwa rental platform side project against its January landlord demo checklist, 2-3 h/wk timebox, and synthetic-only data rules (Rule 9).
---
# iwa Landlord Demo Check
1. **Timebox & State check (Rule 5)**: Read `BUILD_STATUS.md` (or `STATE.md`) first. Keep work strictly inside the 2-3 h/wk side-project box; the LifeOS Engine flagship never waits.
2. **Privacy & Synthetic Data check (Rule 9)**:
   - Run `lifeos guard` on all tracked files.
   - Verify that 100 % of tenant names, phone numbers, addresses, unit numbers, and payment rows are synthetic/fictional. Real tenant or landlord data must never enter Git or any AI tool.
3. **Five Landlord Demo Flows**:
   - Homes list (occupied vs. vacant status clear).
   - Landlord, tenant, and unit linking works end-to-end.
   - Rent schedule and instalments calculation passes tests.
   - Pending vs. confirmed payments view updates cleanly.
   - Repair request submission and triage status works.
4. **Proof logging**: Update `BUILD_STATUS.md` at the end of the session and log the merged PR or test run with `lifeos log proof --area career --proof "<what passed>" --link "<PR or commit>"`.
