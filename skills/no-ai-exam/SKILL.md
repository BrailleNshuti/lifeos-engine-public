---
name: no-ai-exam
description: Run or grade the First-Sunday 60-to-90 minute Monthly No-AI Exam and update logs/skills.md.
---

# Monthly No-AI Exam Protocol

## When to Use
- On the **first Sunday of every month** (60 to 90 minutes, strictly offline / zero AI).
- When the user asks to generate, take, or grade a timed no-AI skill test.

## Workflow
1. **Generate the Exam Paper**:
   ```powershell
   python -P -m lifeos.cli --home C:\Users\you\lifeos exam --draft
   ```
   Give the user **only the questions** (`reviews/exam-YYYY-MM.md`). Never show worked solutions before the user has submitted their own attempt (Law 3).
2. **Grade Strictly with Rubric**:
   - Part 1: 3 short-answer retrieval questions (30 pts)
   - Part 2: 2 quantitative/derivation problems (30 pts)
   - Part 3: 1 from-scratch code task written without AI/autocomplete (25 pts)
   - Part 4: 1 explain-it-aloud oral question (15 pts)
3. **Record the Score & Elevate Skill Level**:
   ```powershell
   python -P -m lifeos.cli --home C:\Users\you\lifeos exam --score-skill "Python engineering" --score-pct 85 --link "reviews/exam-2026-11.md"
   ```
   - A score **$\ge 80\%$** automatically elevates the skill to **Level 3 (Timed Solo, No AI)** in `logs/skills.md` and appends a proof row to `logs/proofs.csv`.
   - Any topic scoring **$< 70\%$** is listed under *Three Weakest Points* and repeats next month.
