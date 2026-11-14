# Prompt Lab runner · design · 2026-11-13
Design only, no code yet (tests first). The engine holds the generic mechanism only: no card text, no personal data. Cards and results live in the private data repo.

## Flow
`lab check` validates a card. `lab pack` prints its prompt and five test inputs; you paste them into the work console, one fresh request per test (never chained in one chat), then paste each output into a results file. `lab score` scores that file offline, prints n/5 and logs one proof.
The runner never calls a model: it reads and writes text only.

## Card file (from templates/prompt-card.md; a label starts a line and its value runs to the next label)
```text
# Prompt card · <name> · v<n> · <YYYY-MM-DD>
Goal: <one sentence>
Used in: <tool>
OK: <where the permission to run it there is recorded>
Role and context: ...
Inputs (placeholders only): {{a}} {{b}}
Rules: ...
Output format: ...
Examples (made-up): ...
Tests (made-up data): <prose, ignored>
{{b}}: <value shared by all five tests; may span lines>
T1 <title>
{{a}}: <this test's value; replaces a shared one>
check: <method> <argument>   (one or more per test)
pass: <sentence for humans, ignored>
T2 to T5: as T1
Pass when: <prose, ignored>
Safety check: <a human statement; no tool can verify it>
Score: <kept by hand; the runner never edits a card>
```
- The prompt part starts at `Role and context:`, ends on the line before `Tests` and is pasted as written. The `check:` lines are the answer key the runner reads; `pass:`, `Pass when:` and the `Tests` prose are for humans.
- `lab check` refuses unless: exactly five tests; each has a `check:` line; every `{{x}}` in the prompt part is declared in `Inputs` and has a value in every test; `OK:` and `Safety check:` are filled; the guard finds no class C data.
- Two hashes (sha256, 12 hex; line endings and trailing spaces normalised): `prompt` = the prompt part, `tests` = from `Tests` through `Pass when`. A test edit changes `tests`, which makes a new version of the card (card rule). Approve the answer key, and note its `tests` hash, ahead of the first run (rules 6, 7).
- Today's cards differ in three ways: the header fields share one line and the permission label is named differently; a test has `in:` for its one input while shared data sits in prose; `pass:` is prose only. One edit pass fixes all three (decision 4).

## Commands (offline; exit 0 ok, 1 refused, 2 bad input, like `guard`; `<card>` is a path or a name in prompts/cards/)
| command | does |
|---|---|
| `lifeos lab check <card>` | validates the card and runs the guard; prints both hashes and about how many tokens one full run sends |
| `lifeos lab pack <card> [--filled] [--results FILE]` | runs `check` first; prints the prompt once, then `T1` to `T5` with their values (ids only: never titles, `check:` or `pass:` lines). `--filled`: five finished prompts instead. `--results FILE`: writes the empty results file with the hashes, never overwrites |
| `lifeos lab score <card> <results> [--dry-run]` | runs `check` first; scores, prints each test and n/5, logs one proof (see Logging), prints the `Score:` text to paste into the card by hand |

## Why the runner does not call a model (rule 9; data classes A public, B personal, C sensitive, D employer: employer tools only)
- rule 9 sends work prompts to the work console, tested only on invented or public text. `claude -p` or `codex exec` from the engine would run them in personal accounts: outside that permission and the work/personal split.
- The gate is a person. "Not sensitive or confidential" is not something the regex guard can decide (a paraphrased real case passes it); a caller in code removes the gate and puts the policy in public code.
- Evidence: the console calls the API directly. `claude -p` and `codex exec` are agent harnesses with their own system prompt, tools and settings, so their scores do not transfer to the console (rule 6).
- A public, standard-library-only engine gets no key, no network and no subprocess in lab code; scoring is deterministic, so tests and CI need no network, and no personal token pool is drawn.
- Enforced, not promised: a layering test fails if a lab module imports `ask`, `delegate`, `mcp`, `subprocess`, `socket`, `urllib` or `http`.
- Accepted cost: five pastes per run and no automatic multi-model bake-off. The results format does not depend on who produced the text, so a later opt-in `lab run` can write the same file (Out of scope).

## Score methods (offline; a test scores 1 only if every `check:` line holds; an empty output scores 0)
| method | argument | passes when | fits |
|---|---|---|---|
| `exact`, `exact/i` | text | the trimmed output equals the text | closed label sets |
| `json` | one JSON object | the whole output is valid JSON equal to it: types strict (`true` is not `1`), a missing or extra key fails, key order ignored | free text to a fixed schema |
| `has`, `lacks` (`/i`) | text | the text occurs / does not occur | key facts; injected-instruction tests |
| `sources` | `<id>=<date> ... max=<n>` | each sentence closes with a citation `[<id>, <date>]` of a declared id and date; at most n sentences | answers from given sources |
| `manual` | what to verify | `## manual` in the results file says `T<n>: pass`; without a verdict `score` prints the rest, logs nothing, exits 1 | what a script cannot judge, e.g. whether a cited source states the fact |
Never a model as judge (rule 6). An output is only trimmed before a check; nothing else is normalised.

## Results file (under logs/lab/ in the data repo; `pack --results` writes it, you fill it, nobody edits it afterwards)
```text
# Lab results · <name> · v<n>
prompt: <hash>   tests: <hash>
model: <exact id shown in the console>   date: <YYYY-MM-DD>
settings: <free text, e.g. temperature>   tokens: <in>/<out>   (optional)
## T1
<output pasted unchanged; the same for ## T2 to ## T5>
## manual
T<n>: pass|fail <reason>
```
`score` reads the header keys up to `## T1`, then splits blocks on lines equal to `## T<n>`; a missing, repeated or unknown block refuses. Both hashes must equal the card's, so results of an edited card cannot be scored against it.
Later slice: paste the console's request export once under `## request`; `score` reads the model id from it and checks the prompt against the hash (`export checked`, else `typed by hand`). Assumes the console offers an export: unverified.
Results are self-reported: the hashes prove the card did not change, not that the console wrote the text.

## Logging (rule 1: a score is a proof)
- `score` runs the guard on the results first, API-key patterns included; a BLOCK exits 1 and logs nothing.
- One row in logs/proofs.csv: area `lab`, text `<card> v<n>; <k>/5; <model>; run <i>; <export checked|typed by hand>; results <hash>; lifeos <version>`, link = the results file (`lifeos week` already counts proofs by area). The hash is the dedupe key (a second `score` of the same file logs nothing) and shows later edits. It goes through the engine's single CSV writer (architecture review, finding 2; `lifeos log` is the planned front end); until that exists `score` only prints.
- `run <i>` counts earlier results files of the same card, version and model, and `score` prints their scores, so retries and noise show. The same `tests` hash with a new `prompt` hash prints "same tests as an earlier prompt version: not independent evidence".
- No ledger row: the run is not an engine call, saves no minutes, and the console's tokens are not the personal budget; a row would only pad the week's ledger-line count.

## Out of scope
- Any model call from the runner, model-graded scoring, running model-written code, style or language-quality scoring, automatic prompt tuning.
- Router, dashboard, scoreboard; a pass rule across runs (decision 5).
- Cards or results in this repo: `examples/` gets one made-up card and results file, written fresh.
- Telling invented input from paraphrased real input: the guard cannot, so the Safety check line stays a human statement.
- A later `lab run`: only for cards with `Venue: personal`; no field means work and never reaches an adapter; a test enforces it.

## Build order (tests first; add each module to LAYER in tests/test_layering.py)
1. `labcard` (parse, hashes, pack text) and `labscore` (the methods), layer 0, on made-up fixtures: parse and refusals; hashes stable across line endings, trailing spaces, BOM and UTF-16; each method passes, fails and meets its edge cases; the no-model layering test.
2. `lab` (check, pack, score; layer 1) and the `cli` wiring, with the README row (and, if decision 2 is yes, the roadmap wording) in the same PR; logging once the shared CSV writer is on main.
3. Later: a console import file (`--csv`, if the console has one), the request-export check.

## Open decisions for the owner
1. Console outputs on made-up inputs: class B, kept in the data repo under logs/lab/ (rec), or class D, kept in employer tools? Ask the employer if unsure.
2. Replace the README v0.3 roadmap wording (cards run through `claude -p` and `codex exec`) with this paste-and-score flow? (rec: yes, one line)
3. Allow a later opt-in `lab run` through `lifeos ask`, only for cards marked `Venue: personal`? (rec: not before the first real scores)
4. Edit the three picked cards before their first run (split the header, rename the OK label to `OK:`, add value lines and `check:` lines)? (rec: yes, one data-repo PR)
5. Count a card as passed only after two runs with the same hashes, one run being only "scored"? (rec: yes)
