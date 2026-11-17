---
name: work-prompt
description: Build and test a prompt for the user's job in the Prompt Lab. Use only after the employer's written OK is recorded in now.md, and never with work data.
---
# Work prompt (Prompt Lab)
0. Check now.md: is the Prompt Lab approved by the employer? If not, stop and say so.
1. Write a prompt card from templates/prompt-card.md: goal, role, input placeholders, rules, output format, two made-up examples, five made-up test cases, each with a pass rule.
2. When asked, run the tests (`claude -p` or `codex exec`), score each against its pass rule, fix and re-run until five of five pass, and record the score.
3. Six-point check before it goes to work: no client or person names, no data, no internal document text, no prices or deals, no credentials, nothing marked internal. If one fails, stop.
4. Real work results never come back into LifeOS; the card only gets a field note: used, worked or not.
