# Security and privacy model

What the engine promises, what it does not, and the test behind each promise. The test names are checked by
`tests/test_security_doc.py`: a promise whose test is renamed or deleted fails the build.

## Promises

| Promise | Test |
|---|---|
| Identifiers (IBAN, cards, ID numbers, keys, secrets) are blocked before a model call | `tests/test_canary.py::test_outbound_canaries_are_stopped_before_any_model_is_called` |
| The guard has no false alarms on look-alike text (SHAs, UUIDs, timestamps) | `tests/test_guard_negatives.py::test_a_whole_document_of_harmless_lines_is_clean` |
| The guard's score is real: it drops when the guard is blind | `tests/test_canary.py::test_the_score_is_real_it_drops_when_the_guard_is_blind` |
| Sensitive data classes are routed to local-only providers | `tests/test_policy.py::test_check_provider_allowed_enforces_local_only_for_sensitive_and_blocks_secret` |
| An editing, deleting, swapping or forged record in the run ledger is detected | `tests/test_ledger_attacks.py::test_deleting_a_non_final_record_is_caught` |
| A cut tail or rewritten last record is detected with an anchor | `tests/test_ledger_attacks.py::test_rewriting_the_last_record_passes_the_chain_but_not_the_anchor` |
| The input of a past run can be proven unchanged, or the changed file named | `tests/test_replay.py::test_replay_names_the_file_that_changed` |
| Parallel writers never lose a record or break the chain | `tests/test_concurrency.py::test_processes_append_without_losing_or_breaking_the_chain` |
| The weekly cloud budget holds a call before it is sent | `tests/test_governor.py::test_a_call_that_would_cross_the_cap_is_held_before_it_is_sent` |
| Shared copies can be made without the secret (not just masked) | `tests/test_redact.py::test_findings_lines_are_replaced_and_the_result_scans_clean` |
| Pipelines cannot nest or carry private data in their arguments | `tests/test_pipeline.py::test_a_pipeline_cannot_nest_or_hold_secrets` |
| A Windows checkout verifies and behaves like a Linux one | `tests/test_crlf.py::test_the_hash_chain_survives_a_crlf_checkout` |
| Damaged logs never crash a read command | `tests/test_fuzz_logs.py::test_read_commands_survive_garbage_logs` |
| No personal name or private decision id sits in a tracked file | `tests/test_public_hygiene.py::test_no_employer_name_or_private_decision_id_in_any_tracked_file` |

## Not promised

- **The ledger is tamper-evident, not tamper-proof.** Someone who can rewrite the whole file and every copy of the anchor can forge a history. Keep the head hash somewhere you do not edit (a commit message, a proof row).
- **The guard is a pattern checker.** It finds identifiers with a valid checksum or a known shape. It does not understand meaning: a sentence describing your medical history passes. Class C data stays out of every tool by your own rule.
- **Cloud tools process what they read.** The engine sends only the pack you can see with `--dry-run` or `--explain`, but a provider's retention is the provider's.
- **Local models are not audited here.** "Stays on this laptop" means the engine does not send it anywhere; it does not inspect the model server.

## Reporting a problem

Open an issue without the secret in it (describe the shape, not the value). If a real identifier was committed, rotate it first; history rewriting comes second.
