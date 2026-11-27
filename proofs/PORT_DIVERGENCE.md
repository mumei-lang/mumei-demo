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
counterexamples outside the fixture. Those inputs are necessarily biased toward
the buggy contract violation, so a fixed-side port can satisfy every fixture
while still losing fixed-reference state meaning. `run_contract_bench.py` therefore
also builds a solver-backed comparison harness that inlines the reference and
candidate bodies and compares primitive results or struct output fields under
the pinned `requires`. A `matched` result is exact confirming fidelity evidence.
If exact output diverges, the harness reapplies the committed relevance,
rounding and failure-state adjudication; divergence that remains there blocks
acceptance, while divergence confined to those boundary regions is explicitly
inconclusive diagnostic evidence rather than a false positive. Loop-containing
bodies are explicitly unavailable because loop-invariant abstraction can
manufacture a spurious difference even between two copies of the same reference
body. In the recorded corpus, all 70 non-loop exact fixed-reference copies
match; the one loop case is unavailable.

`proofs/output-equivalence-policy.json` records the manual abstraction
adjudications that keep exact equality from demanding correctness in don't-care
or model-boundary regions. SOL02-D11 compares `bid_of` only when a previous
bidder exists, because the no-previous bidder input has no meaningful previous
live-bid record. SOL03-D08 explicitly marks failure-path `owed` as meaningful
state, so a port that clears the amount still owed after a failed transfer
diverges instead of hiding behind failure-sentinel tolerance. TS03-D09 treats
the one-cent truncation/rounding boundary as part of the integer model of
`Math.round`; larger output differences remain divergence. TS03-D03 is the
opposite adjudication: multiplication-before-division is the canonical integer
model, so reordering division first remains meaningful divergence. In the
recorded fixed LLM ports, divergence is therefore 3, 4 and 4 case-runs
respectively (GO01-D04, PY02-D08 and TS03-D03 in every run, plus RS01-D06 in
run 2 and SOL03-D08 in run 3). These are semantic fixed-port errors rather than
correct-port overblocking; the TS03-D09 rounding implementation and SOL02-D11
no-previous-bidder difference are boundary-only inconclusive evidence, not
blocking divergence.

The lint is variant-aware and records high-confidence meaning-loss evidence: silent repair, missing modeled operations, guard folding, self-calls and success-flag rewrites. Confirming replay or matched solver output overrides guard-shape and success-flag lint-only warnings; exact result-state guard folding remains blocking unless output equality matches. Added or removed guard-count warnings remain visible but do not block alone, because legitimate fixed-side translations can differ in guard shape. Neither lint, replay nor output comparison is represented as a formal `refuted` verdict for the original candidate. Replay or output divergence blocks a candidate. Other high-confidence lint blocks when neither semantic check supplies confirming evidence (`still_refutes`/`still_holds` or `matched`), except silent repair, missing modeled operations and self-calls, which are structural fidelity loss even when outputs coincide; inconclusive evidence alone does not rewrite a raw proof. A blocked candidate keeps its raw verifier outcome in the committed JSON but is counted as unsupported/inconclusive evidence rather than verification acceptance. The same harness also keeps proofs under weak or vacuous LLM-generated contracts out of acceptance while preserving their raw verifier outcomes.

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
