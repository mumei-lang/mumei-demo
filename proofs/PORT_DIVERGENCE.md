# Contract bench: why buggy LLM ports passed verification

The three recorded `openai/gpt-6-luna` runs accepted a buggy port **26 times (10, 8,
and 8 per run), across 12 distinct cases**. On the concrete input in each case's
`replay.json`, Mumei's Z3 verifier refuted the buggy reference port but accepted
the corresponding recorded LLM port in all 26 case-runs.

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
assert that your binary is the one that produced the recorded bench scores.

The detector preserves the pinned signature, prelude, and contract and adds
the same concrete input constraints to both ports' `requires`. It records
`diverged` if any replay input refutes the reference and is proven on the LLM
port, `still_refutes` if both refute every supplied input, and `inconclusive`
otherwise. Missing or failed verification is not evidence of divergence. The
inputs include both solver counterexamples and hand-picked counterexamples
rechecked by the verifier; this is not an equivalence proof or a search for
counterexamples outside the fixture. The diagnostic does not change bench scores.

Risky-op lint looks for index/slice, division/modulo, dereference and narrow-cast
patterns represented in both the source function and its buggy reference port.
It warns if no operation of that kind remains in the LLM body, and separately
notes extra conditionals relative to the reference, new ways for an `ok` flag to
be false compared with the reference flag expressions and their branch conditions,
and direct self-calls. These are syntactic clues, not
a language-aware source diff or proof of a silent repair: the model may omit
unrelated source operations, and it may encode a source operation differently.
