# Architecture · 2026-11-13

LifeOS Engine is a dependency-free Python package. Personal state lives in a separate private repository selected by `LIFEOS_HOME`; the engine repository contains code and fabricated examples only.

## Interfaces

- `lifeos` is the command-line interface.
- `lifeos mcp` is a local JSON-RPC/MCP interface over stdin/stdout.
- Both interfaces call the same modules; neither owns business logic.

## Module direction

Imports may point only downward. `tests/test_layering.py` enforces this graph and requires zero cross-module uses of underscore-prefixed APIs.

1. Storage foundation: `store`
2. Core: `home`, `guard`, `check`, `tasks`, `week`, `labcard`, `labscore`
3. Context assembly and offline Prompt Lab: `context`, `lab`
4. Model adapters and guarded recording: `ask`
5. Routing and local CSV work: `delegate`, `sortcsv`
6. Interfaces: `mcp`, then `cli`

## Read and write paths

- `context` reads only the approved core files and one validated task path, and can explain inclusion, trimming, exclusion and SHA-256 provenance (`explain_pack`). For blind reviews (`build_review_pack`), it strips existing `## Result` sections so reviewers see only pre-committed facts.
- `ask` scans the context, calls one adapter (or multiple independent adapters in `run_review`), scans the answer, then passes the result and run metadata to `store`.
- `store` is the only writer for model/task results, ledger rows and immutable execution run records (`logs/runs.jsonl`). It uses atomic sibling temp-file replacement (`os.replace`), suppresses duplicate retry writes, repairs missing final newlines and owns the stable model-call note contract consumed by `week`.
- MCP writes are restricted to task files and the ledger through the same guarded path.
- `sort-csv` is separate: it refuses remote Ollama hosts, existing outputs and outputs inside Git repositories.

## Privacy boundaries

- Ollama and Qwen accept only loopback hosts.
- Reviewed repository scans may use `lifeos-guard: allow`; outbound prompts and model answers may not.
- The scanner catches high-confidence identifiers and secrets. It cannot reliably classify natural-language medical, tenant or employer information.
- Model CLIs run from an empty temporary directory. This reduces accidental context but is not an operating-system sandbox; CLI permissions remain part of deployment configuration.
- Gemini through `agy` receives its prompt as a command argument because that tool does not accept stdin, so the adapter enforces a command-length cap.

## Encoding and files

- Task and log text is UTF-8.
- The guard also scans UTF-8 BOM, UTF-16 BOM and legacy single-byte text.
- `sort-csv` writes UTF-8 with BOM for Excel compatibility and preserves the detected delimiter.
- Files over 1 MB and binary files are reported as skipped rather than silently counted as scanned.

## Verification

CI runs the full pytest suite and the repository guard on Python 3.10, 3.11, 3.12 and 3.13 on Linux, plus Python 3.12 on Windows. The package has no runtime dependency.

## Known limits

- CLI integrations need periodic live smoke tests because external command-line interfaces change.
- Routing is deterministic keyword routing, not an evaluated cost/quality optimizer.
- The privacy scanner is a backstop, not a substitute for the data policy.
- Prompt Lab remains a design proposal until real-use evidence justifies another feature.
