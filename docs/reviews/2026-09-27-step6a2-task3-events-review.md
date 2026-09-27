# Step 6a.2 Task 3B — statistical event adapter review

**Status: ACCEPTED — independent review, root checks, post-commit probes and exact-commit Linux CI passed.** Scope is the pure statistical event/parity adapter, not the result writer, completion seal, validation unlock or actual experiment.

Astra Medium performed simplicity then correctness review; root independently reviewed failure semantics and numerical preservation. No unjustified abstraction was identified. Sol Medium was the sole implementation writer.

## Repaired findings

- CR1 computes its own moments/refusals even if CR2 refuses; it remains report-only. Guard denominators before division.
- Nonfinite provenance describes actual nonfinite/overflow intermediates; finite underflow is not falsely labelled nonfinite.
- Refusal mapping preserves the actual estimator status. Empty vectors cannot hide an incorrect scalar refusal; candidate-floor reasons are forbidden in base events.
- Validate strict chunk IDs, block integers, boolean wins and exact-float raw/excess tuples before NumPy conversion.
- Use the exact verifier arithmetic for near-zero thresholds. Root reproduced a one-ULP difference at scale 1.5 between the two multiplication orders; a nextafter regression covers it.
- Required fixed/triggered records call the frozen scalar independently; partitions and parity validate before the adapter returns.

## Frozen bytes and verification

- Script SHA256: `b673a5eefbd177c029f62ccd4cc8eb4750c138ee16d1c2f23918d2834c38344e`.
- Initially reviewed tests SHA256: `53930d4dc0aefc52c01a3edc96438be77f0b7fe6b6a211eec9a5b839cb3dcf3d`. Test-only follow-up `261e11a` isolates the empty-row mismatch; final test SHA256 `60c67b7b70c161f9dabe5713284a8f968efee2e2310138c0f545b80ba06442ff`. Astra and root independently approved the narrow correction; targeted test, Ruff and explicit mypy passed.
- Astra reconciled the final test hash after Ruff sorted an import, independently reread the final imports/test additions, and approved these exact bytes. Any semantic change requires rereview.
- Root: 1,504 unit tests passed, three Windows platform skips (149.50s); Ruff lint/format, project mypy, explicit script/test mypy and whitespace checks passed. Code committed at `7450d47`.
- Builder: 23 focused tests; Task 2 38 passed (35.45s); Task 3 194 passed, three Windows skips (83.41s); Ruff/mypy/whitespace checks passed.
- Root independently reproduced 2,952 old-code interval outputs exactly, including .90/.95/.99 confidence and win clipping. Baseline SHA256 `c7f54a16ac1bff74ecad328703ffa141d6927e58ef2bf6e4660ebe9127812451`.
- Root's independent unequal-block fraction example yields mean 3/200, sample variance 7/20000, CR1 variance 7/480000 and CR2 variance 7/400000; uncapped effective N is 24 and 20 for six observations. This hand oracle is now covered by tests.

Only scripted or separate-fixture inputs were used. Frozen manifest/digest/estimator and disabled inference are unchanged. No reserved RNG, result artifact or completed-runner attestation was created.


Post-commit probes at `261e11a` caught 8/8 deliberately introduced in-memory faults, including the now-isolated empty-refusal mutation. The source SHA256 remained unchanged. Linux CI for production code `7450d47` passed: 1,507 tests, four pre-existing integration skips (75.84s), Ruff lint/format and mypy clean: https://github.com/Sujayprodduturi/Icarus/actions/runs/36311659571. Native Linux-only checks executed. F11 integration skips remain open. The test-only follow-up CI is tracked separately; no production semantics changed.


Final test-only follow-up `261e11a878182938945bc87f3aaa0de24f6614d8` also passed Ubuntu CI: 1,507 tests, four pre-existing integration skips (144.72s), Ruff lint/format and mypy clean: https://github.com/Sujayprodduturi/Icarus/actions/runs/36311805721. This closes the 3B milestone; 3C and Slice 4 remain separate unfinished work.
