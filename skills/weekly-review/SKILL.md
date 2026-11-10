---
name: weekly-review
description: Draft the Sunday weekly review in the LifeOS data repo from its logs. Use on Sundays, when asked for the weekly review, or from the scheduled review task.
---
# Weekly review draft
1. Run `lifeos week` (or `lifeos week --week YYYY-Www`). Use only its numbers. If a number is not in the logs, write "no data"; never estimate.
2. Copy templates/weekly-review.md to reviews/YYYY-Www.md. Fill item 1 (numbers) and item 2 (proof links).
3. Items 3 to 6 are the user's questions. Add one short observation each from the logs and now.md, marked "draft".
4. Item 7: propose next week's Top 3, one per bet in now.md, each with a done-when.
5. Item 8: propose one system fix, the smallest change that would have saved the most time.
6. Brake check: system time over its cap two weeks in a row means proposing to pause the newest part.
7. Work on branch claude/review-YYYY-Www, open a pull request, never push to main.
