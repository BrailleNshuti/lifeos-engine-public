# First live debate: what happened (2026-11-19)

One real run of `lifeos debate` with three cloud seats, on a public question, in a throwaway made-up home (no personal data).
Question: can `os.replace` fail with `PermissionError` on Windows when another process has the destination open for reading, and
what is the safest way to rewrite a log file other processes may read? Seats: Claude, Codex, Gemini (labels A, B, C after the seeded shuffle).

## What worked

- 9 of 9 seat calls succeeded (3 rounds, 3 seats); every answer is stored with its sha256; `lifeos verify`: chain ok, 17 records.
- Round 1 sent the identical pack (about 230 tokens) to all three. No prompt held a seat name or a recorded hash (checked by tests; not re-checked by hand on this run).
- Objections: 14 raised (Claude 4, Codex 4, Gemini 6); 10 counted; 4 set aside as opinions; 0 ignored for a bad target or over the cap.
- Verdicts over 51 claim rows: FELL 6, OPEN 0, SURVIVED 45 (3 revised after an objection, 42 unchallenged and so not verified).
- Defences: Claude conceded 5 of 5, Codex conceded 1 and revised 2, Gemini revised 2.
- Agreement logged, not used: 1 claim.

## What it showed that the tests did not

1. **The scoring unit was wrong.** `claims_of` split an answer into sentences, so a 5-item answer became 30 "claims" ("You can check this yourself." was one). Codex: 4 items, 10 claims; Gemini: 5 items, 11. Fixed afterwards: a numbered point with its sub-lines and evidence is one claim, so the same three answers now give 6, 5 and 6 claims (the closing "what would prove me wrong" line counts as one).
2. **The evidence gate rewards asserting evidence.** The Claude seat wrote `evidence: none ... I could not run the test because Bash is disabled in my session` and `kind: opinion`, so all 4 of its objections were set aside, correctly by the rules. Codex and Gemini wrote "reproducible test on Windows + Python 3.12.10" and were counted. The engine checks for a pointer, not truth, and cannot tell a test that was run from one that was only described.
3. **The seats concede or revise; none rebutted with evidence.** That is why there is no OPEN verdict. Cooperative models make a debate quieter than the design assumes; whether a stricter prompt changes that is not tested.
4. **The Claude seat runs without a shell**, so it cannot produce run evidence. Seats do not have equal means.

## Not verified

The technical answers themselves. Nothing in this run shows that `os.replace` fails when a reader holds the file; that needs a test on a Windows machine (see STATE.md, the write-failure diagnosis).

## Next

Run one more debate with the corrected scoring unit and compare the verdicts. The figures above are from the run as it happened, with the old sentence unit.
