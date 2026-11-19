---
name: build-in-public
description: Draft a 20-minute weekly Build-in-Public proof post (LinkedIn/GitHub) and monthly engineering case study from verified logs.
---

# Build in Public

## When to Use
- Once a week (from Gate 2 or whenever shipping major portfolio milestones) to draft a 20-minute LinkedIn/GitHub post.
- Once a month to draft an engineering case study from verified proofs.

## Rules (Law 1, Law 8 & Law 9)
1. **Every post must carry a real proof**: What you built · the number that proves it · one lesson.
2. **Zero private or work data**: Run `lifeos guard` on every draft. Never mention employer internal details without written OK; never mention `iwa` private details without co-founder OK.
3. **Publishing is L3**: The agent drafts `reviews/post-YYYY-Www.md`; the user edits and posts manually.

## Command
```powershell
python -P -m lifeos.cli --home C:\Users\you\lifeos showcase --draft
```
