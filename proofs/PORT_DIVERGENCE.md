# Contract bench: why buggy LLM ports passed verification

Before the fidelity acceptance gate, the three recorded `openai/gpt-6-luna` runs had raw verifier accepts of a buggy port **26 times (10, 8, and 8 per run), across 12 distinct cases**. On the concrete input in each case's `replay.json`, Mumei's Z3 verifier refuted the buggy reference port but accepted the corresponding recorded LLM port in all 26 case-runs. The committed rows still keep those raw verifier outcomes; the benchmark's fidelity projection excludes every one of the 26 candidates from verification acceptance and counts it as unsupported/inconclusive evidence instead.

| Case | Runs | Primary mechanism in the recorded body |
| --- | --- | --- |
| GO01-D04 | 1, 2, 3 | **Operation removed.** Replaces the unconditional `parts[3]` access with a branch on `has_sku`; returns a constant or the modeled SKU instead of indexing. |
| GO02-D03 | 1, 2, 3 | **Guard added.** Rejects a negative `top` and clamps a too-large one instead of passing it directly to `slice_to`. |
| PY02-D04 | 1, 2, 3 | **Guard added.** Returns an error for short rows instead of indexing column 3. The contract also requires success for long rows, so it is not enough to always return an error. |
| PY03-D05 | 1, 2, 3 | **Success convention changed.** Keeps the computed start but returns `ok: false` for negative offsets, making the `result.ok => …` postcondition vacuous on the witness. |
| PY04-D11 | 1 | **Guard added.** Returns false for an absent document before calling modeled `deref`. |
| RS03-D03 | 1, 2, 3 | **Guard added.** Rejects a zero determinant before division. |
| RS03-D04 | 1, 2, 3 | **Guard added.** Returns an error when the product is out of the i32 range instead of succeeding with the modeled overflow. |
| SOL01-D03 | 1, 3 | **Guard added.** Returns the default share price on zero supply instead of dividing by zero. |
| SOL03-D07 | 2 | **Self-call substituted.** Replaces the successful constructor body with a same-argument call to itself. Mumei accepts that port on the witness; this is not evidence of an implemented repair or termination. |
| TS01-D03 | 1, 3 | **Guard added.** Tests `found` before dereferencing the task. |
| TS01-D07 | 1 | **Fallback added.** Returns a valid default for a present nonnumeric input instead of returning the modeled invalid priority. |
| TS02-D11 | 2 | **Guard added.** Tests `found` before dereferencing the link and returns an error otherwise. |

The primary mechanisms are exclusive in this table: guards account for 18 of the
26 accepts, operation removal and a changed success convention account for 3
each, and the fallback and self-call account for 1 each. Six cases were accepted
in all three runs; the other six were run-dependent. The table classifies observed
body changes, not the verifier's internal reason for accepting any particular body.

## Reproduce

```sh
python3 scripts/run_port_divergence.py --mumei-bin ../mumei/target/debug/mumei
```

Add `--json` to see witness values and provenance, the two replay verdicts and
their diagnostics, and the lint findings. Add `--model` to select a single
recorded model. No provider credentials, native specimen execution, or benchmark
regeneration are needed. The command uses the verifier you supply; it does not
assert that your binary is the one that produced the recorded bench scores. To annotate already committed benchmark rows without calling a model, use `python3 scripts/run_contract_bench.py --fidelity-rescore --mumei-bin <path>`; the command is idempotent, preserves raw outcomes, and records the replay verifier identity separately from the original bench verifier.

The detector preserves the pinned signature, prelude, and contract and adds
the same concrete input constraints to both ports' `requires`. It records
`diverged` if any replay input refutes the reference and is proven on the LLM
port, `still_refutes` if both refute every supplied input, and `inconclusive`
otherwise. Missing or failed verification is not evidence of divergence. The
inputs include both solver counterexamples and hand-picked counterexamples
rechecked by the verifier; this is not an equivalence proof or a search for
counterexamples outside the fixture. `run_contract_bench.py` uses the same lint and replay evidence as a fidelity acceptance gate for newly verified LLM ports. The lint is variant-aware and records high-confidence meaning-loss evidence: silent repair, missing modeled operations, guard folding, self-calls and success-flag rewrites. Confirming replay overrides lint warnings except exact success/result-state guard folding, which is high-confidence meaning loss. Added or removed guard-count warnings remain visible but do not block alone, because legitimate fixed-side translations can differ in guard shape. Neither lint nor replay is represented as a formal `refuted` verdict. Replay divergence blocks a candidate. Other high-confidence lint blocks when replay does not supply confirming evidence (`still_refutes` for buggy or `still_holds` for fixed); inconclusive replay alone does not rewrite a raw proof. A blocked candidate keeps its raw verifier outcome in the committed JSON but is counted as unsupported/inconclusive evidence rather than verification acceptance. The same harness also keeps proofs under weak or vacuous LLM-generated contracts out of acceptance while preserving their raw verifier outcomes.

The JSON report also keeps unresolved verifier outcomes and measurement separate:
unsupported input/generated output or capability, residual inconclusive outcome,
environment failure and budget exhaustion are independent counts. Reference-port
verdicts are recorded once per case/input because they are reused across accepted
rows; LLM-port verdicts are recorded per accepted row/input. Missing or invalid
generated bodies and pre-verifier input failures remain unsupported but are not
expected verifier-call measurement slots. Verifier wall time and declared timeout
budget exclude report rendering and replay orchestration.

Risky-op lint looks for index/slice, division/modulo, dereference and narrow-cast
patterns represented in both the source function and the reference port for the
same variant. In this buggy-side report that is the buggy source/reference pair; a
fixed candidate is instead compared with the fixed source/reference pair.
It warns if no operation of that kind remains in the LLM body, and separately
notes extra conditionals relative to the reference, new ways for an `ok` flag to
be false compared with the reference flag expressions and their branch conditions,
direct self-calls, unconditional-success rewrites of a guarded failure branch,
and exact token-level matches with the fixed reference port. In the recorded runs
the fixed-reference rule fires three times, which is high-confidence evidence of
silent repair rather than a semantic proof: the model may omit unrelated source
operations, encode a source operation differently, or write an equivalent repair
that does not match the reference token pattern. When the exact fixed-reference
rule fires, the more generic added-guard warning is suppressed so one mechanism is
not double-counted; older output may classify the same rows only as added guards.
The JSON `lint_counts` total
counts warning instances rather than misaccepted case-runs: one accepted port can
carry several warnings, so the lint total (41 in the recorded runs) is not
expected to equal the 26 primary-mechanism rows in the table above.
