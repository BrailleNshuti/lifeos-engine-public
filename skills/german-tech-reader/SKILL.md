---
name: german-tech-reader
description: Break down technical or administrative German texts (A1-B2 bridge), extract compound nouns and verb frames, and run an attempt-first retrieval quiz. Never use with confidential work data.
---
# Technical German Reader (Attempt-First Protocol)
1. **Safety check first (Rule 9)**: If the German text comes from work and contains client names, internal deals, or confidential data, refuse and remind the user to run it in the employer's approved tools or redact all names/numbers first.
2. **Attempt-first gate (Rule 3)**: Ask the user for their 1-2 sentence guess of what the paragraph means before translating anything.
3. **Sentence surgery**:
   - Highlight the conjugated verb (Position 2) and any separable prefix or infinitive at the clause end (*Satzklammer*).
   - Split every compound noun into its base words with articles (`der/die/das`) and English meaning.
4. **Active retrieval mini-quiz**: Give 3 short recall questions (fill-in-the-article, translate one core verb phrase, and write one simple A1/A2 response sentence) with no answers shown until the user replies.
5. **Log reminder**: Remind the user to log their study block with `lifeos log hours --area german --hours <H> --note "<topic>"`.
