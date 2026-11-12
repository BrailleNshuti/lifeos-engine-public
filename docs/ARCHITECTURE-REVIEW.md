# Architecture review 1 · 2026-11-12 · from reading the code on main (2945d24 + STATE sync)
Scope: lifeos/*.py (1,175 lines, 12 modules), tests (148 after this PR). Everything below was checked in the code, not assumed. Tonight's scheduled run "Architecture doc + fitness tests" writes the descriptive docs/ARCHITECTURE.md; this file is the critique and the ratchet.

## What is sound (keep)
- The module graph has no cycles and now has an enforced direction: core (home, guard, check, tasks, week) → context → ask → delegate, sortcsv → mcp → cli. tests/test_layering.py fails if an import points up or sideways, or if a module imports cli or (except cli) mcp.
- The guard sits below everything that sends or writes, so no feature can bypass it by import order.
- One module per command, short functions, standard library only.

## Findings (ranked; each with evidence)
1. Private names used across modules (7 uses): `_task_file` (ask, delegate, mcp), `_private_patterns` (ask), `_check` (mcp), `_ollama` and `_qwen_model` (sortcsv). A rename inside the owner silently breaks three other modules. Fix: make them public with a clear name (`task_file`, `private_patterns`, `check_text`), then delete the rows from KNOWN_PRIVATE_USES. The test now stops any new case and demands the list shrink.
2. Two writers will touch logs/ledger.csv. Today `ask._record` appends to it by hand (open "a", own newline handling, commas replaced by spaces). Tonight's `lifeos log` adds a second, proper CSV writer. Two writers means two quoting and BOM behaviours. Fix: one `store` module (append_csv_row, append_to_task) used by ask, mcp and log; delete the hand-written append.
3. Stringly-typed contract between ask and week: ask writes `flags: N` inside the ledger note; week.py reads it back with `re.search(r"flags:\\s*(\\d+)")` and a `ASKED` prefix. If either text changes, the Delegation line silently shows 0. Fix: a real column (for example `flags`) or one shared constant and a test that writes with ask and reads with week.
4. `ask.py` has five jobs in 167 lines: model adapters, the guard check, task-result writing, ledger writing, and labels. It is the layer everything above depends on. Fix after finding 2: adapters stay in ask; writing moves to `store`; the guard check stays in `guard`.
5. `estimate_tokens` lives in home.py but is a text utility used by context and cli. Low risk; move when touching home.
6. Encoding is inconsistent on purpose, but undocumented: sortcsv writes UTF-8 with BOM (so Excel opens it), the logs are read and appended without BOM, task files are plain UTF-8. Document it in docs/ARCHITECTURE.md and test each writer's bytes.
7. Windows command-line limit (30,000 characters) is handled for some adapters only via MAX_ARG_CHARS; the rule is not tested for each adapter.

## Suggested order (small, each its own PR, tests first)
1. `store` module with append_csv_row and append_to_task; point ask._record and (when it exists) log at it. Closes 2 and part of 4.
2. Make the 7 private names public; shrink KNOWN_PRIVATE_USES to empty. Closes 1.
3. Put `flags` in a shared constant (or a column) with a round-trip test ask → week. Closes 3.
4. Move estimate_tokens; document encodings. Closes 5 and 6.
Do not start 1 before the `lifeos log` PR is merged, to avoid two people editing the same append code.

## Not changed here
Only docs/ and tests/ are touched: no behaviour change. 148 tests pass, including the four new layering tests; I checked that each fails when its rule is broken.
