# Design decisions

Why the engine is built the way it is. Each decision names what it costs.

## Standard library only
No dependency means no supply chain to audit, no version to pin, and an install that works offline. The cost: some code a library would have done in a line (CSV, JSON lines, argument parsing) is written and tested here. Any new dependency needs a written reason in its pull request.

## The guard blocks, it does not warn
A warning is read once and then ignored. High-confidence patterns (checksum-valid IBANs and card numbers, key formats, assigned secrets) stop the command or the commit. Weak signals (emails, phone numbers) only warn. The cost: false alarms happen, so a line can be marked `lifeos-guard: allow`. `lifeos canary` measures both sides on generated identifiers: how many it blocks and how many harmless texts it wrongly flags. `lifeos history-scan` checks every past commit, because a secret deleted later is still public.

## Nothing is sent before the guard has read it
`ask` builds the exact pack, scans all of it, and only then calls a model. `lifeos canary` plants one identifier of each kind and proves zero model calls and no leak into the logs. The cost: a blocked run does nothing until you fix the text.

## An append-only, hash-chained run ledger
Every run record carries the SHA-256 of the previous line. Editing, deleting from the middle or reordering breaks the chain after that point, and `lifeos verify` says where. A cut-off tail is only detectable against a head hash saved outside the file (`--anchor`), so that limit is stated, not hidden. The cost: a few bytes per record and a lock around writes.

## Replay stores digests, never content
A run keeps a SHA-256 per context file and the task length at that moment. `lifeos replay` rebuilds the input from today's files and compares. The cost: it proves the input is unchanged but cannot recreate a changed one, and older runs are reported as not replayable.

## Blind panel, no model judges another
`lifeos panel` sends the same pack to two to four models, each separately, and compares answers with plain text rules, not with a fifth model. Agreement is where to start checking, not proof. Conflicts and single-voice claims are listed first. The cost: the comparison is crude, so it reports claims, it does not decide who is right.

## The router learns only from enough evidence
Ratings are stored per kind of work. A different model is chosen only with three or more ratings and a full-point lead over the default. Otherwise the default stands. The cost: slow to change, on purpose.

## Budgets in tokens and calls, not euros
The engine drives subscription tools and has no price data, so a euro figure would be invented. The governor holds a call (exit 4) when the weekly cap, a seat's share or a usage-limit rest says so, and `--force` is explicit.

## Logs only grow
Predictions, ratings, vocabulary and the ledger are append-only files. A correction is a new line. The cost: files get longer, and `lifeos digest` shows which parts are used.

## Layers are tested
Every module has a layer and may import only from lower layers (`tests/test_layering.py`). A new module must be registered, so structure cannot drift silently.

## Chaos tests
Torn last line, CRLF checkout, a CSV without a final newline and garbage rows are tested. The first run found a real bug: one damaged line in the run log crashed every reader. It was fixed and the test stays.
