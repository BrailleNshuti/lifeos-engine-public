# Pipelines

A pipeline is a saved list of `lifeos` commands you run as one routine. It lives in your data home as
`pipelines/NAME.json`. Think of it as a checklist the machine can walk for you, and stop when a step fails.

```json
{"steps": [
  {"name": "ledger intact", "argv": ["verify"]},
  {"name": "numbers of the week", "argv": ["digest"], "gate": "continue"}
]}
```

- `argv` is the command exactly as you would type it after `lifeos` (no `--home`: the pipeline adds it).
- `gate` is `stop` (default: a failing step skips the rest) or `continue` (note the failure and go on).
- Steps run with your home as the working folder, so `guard now.md` means the file in your home.

```
lifeos pipeline sunday           # dry run: lists the steps, runs nothing
lifeos pipeline sunday --run     # runs them; exit 1 if any step failed
```

## Rules the engine enforces

- Dry run is the default. Nothing runs without `--run`.
- A pipeline cannot call another pipeline, so there are no loops.
- Arguments are scanned by the guard: a key or identifier inside a pipeline file is refused (rule 9).
- Each step goes through the CLI's own entry point, so every safety check of that command still applies. A step that
  calls a model (`ask`, `panel`) still hits the budget governor and the guard, and still needs your explicit command in the file.
- A pipeline never sends, buys, signs, posts or deletes: no `lifeos` command does (rule 8).

## Examples in `examples/demo-home/pipelines/`

| Name | What it is for |
|---|---|
| `morning` | `week`, `seats`, `guard`: the start-of-day look |
| `sunday` | verify, digest, earn, stale, lint, timeline: the weekly review (rules 10 and 11) |
| `before-push` | guard, lint, verify: three checks before you share anything |

Tests run every example on a copy of the demo home, so none of them rots.
