# lifeos debate: how a blind debate works

Written so that a model can follow it. Nothing here needs a model to decide anything: the scoring is rules.

## The idea

Two to four seats answer one question alone. They then attack each other's answers anonymously, then defend their own.
An idea counts only if it survives on **evidence**. Many seats agreeing is logged but never used to decide: another model
agreeing is not evidence (rule 6, "evidence before confidence").

## Two ways to run it

- **By hand** (any model, any chat): `start`, then `next`, paste each prompt to a seat, save its reply to a file, `record` it, repeat.
- **Automatic**: `start`, then `run --run` asks the seats in order. Without `--run` it is a dry run and sends nothing.

| Command | What it does |
|---|---|
| `lifeos debate start "<question>" --seats claude,codex,gemini [--seed S]` | Makes `debates/<id>/` (`<id>` looks like `D-261120-a1b2c3`). Seats: two to four different ones of claude, codex, gemini, grok, qwen, ollama. Needs a home with a `logs/` folder |
| `lifeos debate next <id> [--round N] [--skip-missing]` | Round 1 prints the one pack every seat gets. Rounds 2 and 3 write one prompt file per seat in `debates/<id>/prompts/`. It waits for seats that have not answered unless `--skip-missing` |
| `lifeos debate record <id> --round N --seat S --file F` | Stores an answer (UTF-8, up to 200 KB) with its sha256 and a chained ledger record. Never overwrites |
| `lifeos debate run <id> [--run]` | Asks the seats round by round. A seat that is not installed, resting or not allowed to see the question is skipped and named, never replaced. A dry run shows only the next round |
| `lifeos debate score <id> [--reveal] [--json]` | Rule-based table, no model. `--reveal` shows which seat wore which label and adds a per-seat scorecard (claims that fell or held, objections raised and landed, defences conceded, rebutted or revised): use it only after the debate, one debate is a small sample |

`run` calls each seat directly instead of through `lifeos delegate`, so the exact text sent is the prompt file and nothing else.

## The three rounds

1. **Answer.** Every seat gets the identical pack. It writes short numbered claims, one per line, each with its evidence,
   and a last line on what would prove it wrong. A **claim** is one numbered point with its sub-bullets and evidence lines
   (or one bullet, or one paragraph; prose with none of these is split into sentences), and the last line is a claim too.
   Only the first 40 claims are shown to others and scored.
2. **Object.** Each seat sees the OTHER answers, relabeled A, B, C in a seeded order, claims numbered (B1, B2). It writes at most
   3 objections per answer: stack several `OBJECTION` blocks in one reply. Blocks beyond 3 for one answer, and blocks that
   point at nothing (an unknown label or claim number), are ignored and reported; only real ones use up the 3.
3. **Defend.** Each seat whose answer drew a counted objection sees only those objections, without authors, as `[O1]`, `[O2]`.
   It replies to each one with a `DEFENCE` block.

## The two formats

```
OBJECTION
target: B2
claim: what is wrong or missing, in one sentence
evidence: a file and line, command output, test id or source with date
kind: evidence
settle: the test or check that would settle it
END
```

`target` is a claim (`B2`) or `B*` / `B` for the whole answer. `kind` is `evidence` or `opinion`.

```
DEFENCE
objection: O1
response: rebut
evidence: what supports your answer
revised: only for revise: the claim as you now state it
settle: the test or check that would settle it
END
```

`response` is `concede`, `rebut` or `revise`. The first defence for an objection counts. An unknown word leaves it unanswered.

## What counts

- An objection counts only if it has a `target` that exists, a `claim`, exactly `kind: evidence`, and checkable evidence.
  Anything else is an **opinion**: set aside, counted in the report, never decisive.
- Checkable means a pointer: a path, file name, test id (`a::b`), URL, call or command in any length, or a number or identifier
  inside a sentence of four or more words. The engine checks that a pointer exists, not that it is true or well chosen.
- A `rebut` or `revise` without evidence counts as a `concede`. A `revise` without `revised` does too.

## The verdicts

Every claim gets a row. Claims nobody challenged with evidence are `SURVIVED (unchallenged, not verified)`: nobody showed
otherwise, which is not the same as true. A counted whole-answer objection gets one `B*` row that covers that answer's claims.

| Verdict | When |
|---|---|
| FELL | any counted objection was conceded, or never answered |
| OPEN | all were answered, and at least one by a `rebut` with evidence: evidence on both sides, which no rule can settle. The table prints the `settle` test, or the two pieces of evidence to compare |
| SURVIVED | no counted objection, or each one answered by a `revise` with evidence. A revision is shown in the row: read it, it can change what the claim says |

The table ends with `Agreement (logged, not used)`: claims two or more seats made. It never changes a verdict.

## What keeps it blind, and what does not

- The label order comes from a stored seed and is written only to `debates/<id>/debate.json`. No prompt carries it. Round 3
  does not show labels at all. In round 2 a seat can tell which label is its own by the one it is not shown; that is all it learns.
- Known provider and model names and 64-character hashes are replaced before another seat reads an answer. A question that names
  a provider is refused. A name that is not on the list, or a recognisable writing style, is not removed.
- Every prompt and every answer goes through the privacy guard (keys, IBANs, cards, ID numbers), and a question or prompt that looks
  sensitive stays on local seats.
- `debate.json`, the round 1 pack and each answer are hashed into the chained ledger. Every command refuses a broken chain or a
  changed `debate.json` or pack, and `next`, `run` and `score` refuse a changed answer file.

## Seats concede

The evidence gate checks that a pointer exists, not that it is true: a seat that writes "I ran this test" is counted, and one that
says "I could not run it" is not. In live runs the seats mostly conceded or revised and rarely rebutted, and there were zero OPEN verdicts in the three live runs recorded so far (`docs/DEBATE-LIVE-RUN.md` covers the first two).
One trial changed only the round 3 prompt to require a rebuttal to cite a command the seat had actually run (with its first output
lines). Scoring was untouched. Result on a made-up benchmark question with three seats: zero OPEN verdicts, zero rebuttals; two seats
revised or conceded every counted objection, and the third timed out in round 3, so the six objections raised against its answer stayed unanswered. The Claude
seat has no shell and said so. One debate is a small sample; the stricter prompt was not adopted.

## What it cannot do

It does not know who is right. Two seats can both bring real evidence: that is OPEN, and a test or a person settles it. Evidence that
exists but is wrong still counts as evidence, and a determined seat can write a pointer that proves nothing.
