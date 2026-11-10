---
name: lifeos-task
description: Create a LifeOS task file from one sentence. Use when the user writes "task: ..." or wants to hand a job to another model.
---
# LifeOS task from one sentence
1. In the LifeOS data repo run `lifeos task new "<sentence>"`. If the command is missing, write tasks/T-YYMMDD-name.md from templates/task.md.
2. Fill route and level from rules.md. Levels: L0 think, L1 organise, L2 change the user's repos on a branch, L3 anything in the world (needs the user's yes).
3. Ask the user for one thing only: the done_when line. Never invent it.
4. Under Context, add links to the files that matter, never pasted text.
5. Never write class C data (ID, bank, passwords, health, tenant data) or employer work into LifeOS.
6. Reply with the file path and the single question about done_when.
