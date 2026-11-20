---
name: demo-readiness-check
description: Check a small side project against its demo checklist, a weekly timebox and synthetic-only data rules before showing it to someone.
---
# Demo Readiness Check
Example project: "Maple Rentals", a made-up rental-management demo. Replace the flows below with your own.
1. **Timebox and state**: read `BUILD_STATUS.md` (or `STATE.md`) first. Keep the work inside the weekly side-project box; the main project never waits.
2. **Privacy and synthetic data**:
   - Run `lifeos guard` on all tracked files.
   - Confirm that every name, phone number, address and payment row in the demo is made up. Real personal data must never enter Git or any AI tool.
3. **Demo flows** (example set):
   - A list of homes shows occupied and vacant status clearly.
   - Owner, tenant and unit linking works end to end.
   - Rent schedule and instalment calculations pass their tests.
   - A pending versus confirmed payments view updates cleanly.
   - A repair request can be submitted and triaged.
4. **Proof logging**: update `BUILD_STATUS.md` at the end of the session and log the merged PR or test run with `lifeos log proof --area lab --proof "<what passed>" --link "<PR or commit>"`.
