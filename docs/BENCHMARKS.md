# Three benchmark lanes

These lanes measure different capabilities. There is no combined score:
proving a contract, accepting a native object, and finding a bug without a
supplied contract are not interchangeable.

## Before the P0 merges

| Lane | Corpus | Result | Measured (UTC) | Tool HEAD |
| --- | --- | --- | --- | --- |
| A — Source-contract | 71 paired reference `.mm` ports | **71/71** buggy refuted; **71/71** fixed proven; **71/71** vacuity controls rejected | 2026-11-24 | Core [`3b8647aa`](https://github.com/mumei-lang/mumei/commit/3b8647aa32083f8cfa135e56b4dc65cb9f117b93) |
| B — Source→machine TV | Same 71 pairs (142 variants) | **71/71 (100%)** buggy rejected at source verification; **43/71 (60.6%)** fixed accepted; **12/142 (8.5%)** confirmed outside profile (0 buggy, 12 fixed) | 2026-11-24 | Core [`3b8647aa`](https://github.com/mumei-lang/mumei/commit/3b8647aa32083f8cfa135e56b4dc65cb9f117b93) |
| C — Existing-code audit, no LLM ([recorded](../specimens/AUDIT_SUMMARY.md)) | 171 defects in 16 specimens | **10/171 (5.8%)** detected; **8/16 (50%)** fixed specimens had false alarms (29 alarms) | 2026-11-03 | Core [`36eb5346`](https://github.com/mumei-lang/mumei/commit/36eb5346fbe3d401cf3229cd17739fa28c8bbf3f); Agent [`e8be5272`](https://github.com/mumei-lang/mumei-agent/commit/e8be527273238327ad76847bc271d56bd8876b33) |
| C — Existing-code audit, LLM ([recorded](../specimens/AUDIT_SUMMARY_WITH_LLM.md)) | Same 171 defects | **12/171 (7.0%)** detected; **16/16 (100%)** fixed specimens had false alarms (211 alarms) | 2026-11-03 | Core [`36eb5346`](https://github.com/mumei-lang/mumei/commit/36eb5346fbe3d401cf3229cd17739fa28c8bbf3f); Agent [`e8be5272`](https://github.com/mumei-lang/mumei-agent/commit/e8be527273238327ad76847bc271d56bd8876b33) |

Lane A uses the contract benchmark's existing verifier and vacuity control
on the reference ports, not the LLM arms. The other arms and modelling
limitations are in the [contract benchmark report](../proofs/RESULTS.md).
In Lane C, “detected” requires a match by file, function and defect category;
the false-alarm rate is the share of fixed specimens with at least one
finding scored as a false alarm, not the share of audit findings.

## After the P0 merges

| Lane | Corpus | Result | Measured (UTC) | Tool HEAD |
| --- | --- | --- | --- | --- |
| A — Source-contract | Same 71 pairs | **71/71** buggy refuted; **71/71** fixed proven; **71/71** vacuity controls rejected | 2026-11-25 | Core [`a0fc10fd`](https://github.com/mumei-lang/mumei/commit/a0fc10fdefb3ba572336ce7be435c56998adac12) |
| B — Source→machine TV | Same 71 pairs (142 variants) | **71/71 (100%)** buggy rejected at source verification in both runs; **39/71 (54.9%)** then **42/71 (59.2%)** fixed accepted; **11/142 (7.7%)** then **12/142 (8.5%)** outside profile (all fixed) | 2026-11-25 | Core [`a0fc10fd`](https://github.com/mumei-lang/mumei/commit/a0fc10fdefb3ba572336ce7be435c56998adac12) |
| C — Existing-code audit, no LLM | Same 171 defects in 16 specimens | **11/171 (6.4%)** detected; **9/16 (56.25%)** fixed specimens had false alarms (28 alarms) | 2026-11-25 | Core [`a0fc10fd`](https://github.com/mumei-lang/mumei/commit/a0fc10fdefb3ba572336ce7be435c56998adac12); Agent [`569f478f`](https://github.com/mumei-lang/mumei-agent/commit/569f478fe5b35f13809338c2071680e17cbe36b3) |
| C — Existing-code audit, LLM | Same 171 defects | Not remeasured; no comparable LLM run was available | — | — |

## Lane B: original baseline breakdown

Of the 71 buggy ports that Z3 refuted, **all 71** stopped at fresh bundle
source verification; none reached machine TV. This is a rejection rate for
the pipeline, not a claim that the machine checker found the bugs.
Of the 71 fixed ports that Z3 proved:

- **43** had successful `accept-object` descriptors with the target atom
  equivalent within profile.
- **12** were outside a bounded profile (**16.9%** of fixed variants): 1 at
  the LLVM snapshot check, 11 at machine TV (7 unsupported instructions,
  3 unsupported signatures, 1 division trap).
- **10** were rejected at the bundle's source postcondition recheck, despite
  the earlier Z3 proof. This is a source-check disagreement, not an object
  mismatch.
- **6** had inconclusive source/LLVM rechecks. No object mismatches,
  environment errors or timeouts were observed on either variant.

Overall, **28/71 (39.4%)** fixed variants were not accepted. That includes
source rejections and inconclusive attempts as well as the 12 outside profile.
Unsupported and inconclusive attempts don't count as rejections. The low
outside-profile rate across all 142 variants doesn't imply high machine-TV
coverage: the buggy variants stopped before TV.

## Lane B: P0 remeasurement

The two full runs on the new revision took 116.6 and 57.4 seconds.
Both had 10 fixed source-recheck rejections, with no LLVM or object
mismatches, environment errors, or per-command timeouts. Inconclusive fixed
results fell from 11 on the first run to 7 on the repeat. On the repeat,
`GO01-D05`, `RS01-D04`, and `RS03-D02` returned to accepted, and
`RS03-D03` returned to outside profile (`division_trap`). The repeat's
remaining difference from the baseline was `PY02-D02`, which Core
reported as inconclusive at machine TV rather than accepted.

The first run overlapped other CPU-heavy work. The same tool revision
returned different verdicts on repeat, so the first acceptance drop
is not a stable regression. The runs do not isolate the cause of the
remaining difference or establish a change in machine-TV semantics.

## Reproduce the live runs (A and B)

From the demo root with a built Linux x86-64 Mumei CLI and a C linker:

```sh
python3 scripts/run_machine_tv_bench.py --mumei-bin ../mumei/target/debug/mumei
```

The original run used demo corpus HEAD `67b59e2812c51428a289687421fa454455826116`.
The remeasurement used demo HEAD
`f4a9426d22004005fdeb2e6b9cc90fc88c4c661f` with identical reference-port input
hashes. Both used fresh builds of the corresponding Core revisions
(Mumei 0.6.23, GCC 11.4.0), with four workers, a 120-second per-command
timeout, and no model calls. The command prints the Z3-versus-native cross-tab and
writes per-variant outcomes, stages, timings, input hashes and tool
identity to `reports/machine_tv_bench.json` by default. Its summary separates
accepted refuted buggy ports (false acceptance), fresh source rejection of a
proven fixed port (false positive), LLVM/object translation mismatches,
unsupported profile outcomes, inconclusive outcomes, environment failures and
budget exhaustion. `measurement.source_verification` covers the Z3 variant
checks and vacuity control; `measurement.native_pipeline` covers the executed
native build, acceptance and diagnostic-recheck commands. Both report measured
seconds and declared per-command timeout budget with measured-versus-expected
call coverage, so older or partial rows do not look fully instrumented. Use a
separate output path for the repeat so the first report is preserved:

```sh
python3 scripts/run_machine_tv_bench.py --mumei-bin ../mumei/target/debug/mumei \
  --output reports/machine_tv_bench_repeat.json
python3 scripts/compare_machine_tv_runs.py \
  reports/machine_tv_bench.json reports/machine_tv_bench_repeat.json \
  --output reports/machine_tv_bench_diff.json
```

The comparison is evidence, not a verdict promotion: it keeps the first and repeat
case diagnostics separate, counts outcome and unresolved-kind transitions by
variant, and records the per-stage command status/timing differences beside each
changed case. Missing cases and changed verifier, settings or host metadata stay
visible in the machine-readable diff instead of being reconciled away.

## Lane B: focused repeat-stability smoke

`scripts/check_machine_tv_stability.py` runs a small fixed matrix twice in the
same job with the same inputs and toolchain, then compares the two reports.
It fails only on changed input identity, changed case presence, outcome or
unresolved-group transitions, stage-result transitions, or false acceptance.
Timing-only differences stay in the machine-readable diff and CI summary.

The smoke is a reliability diagnostic, not a full benchmark replacement and
not a proof grade or unified verdict. It does not hard-code expected outcomes,
so a future coverage improvement can change an outcome in both runs without
being treated as instability. Unsupported and inconclusive results remain
unresolved evidence, never accepted outcomes. Reports are CI artifacts only;
committed benchmark evidence is not rewritten.

The native path appends only a constant, unrelated `main` to satisfy the
bundle entry requirement; the original contract and target atom are unchanged.
It passes the manifest SHA-256 from the freshly built bundle to
`accept-object`. A zero exit, a source proof, or a diagnostic TV recheck
alone is not acceptance: the descriptor must bind that build ID, report
checked source→machine TV and mark the benchmark atom equivalent. The
baseline measures these hand-written ports, not translation from the
original specimen languages, optimized builds across different profiles,
descriptor or producer authenticity, or runtime behavior.

## Lane C: P0 remeasurement

The no-LLM audit used the same corpus and adjudication hashes as the
original run, including audits of both the buggy and patched copies.
The additional detection was a TypeScript division-by-zero finding
(`TS03-D03`); Python detection stayed at 1/41. The new Agent marked some
Python specimens that were previously verified as unverifiable. That
changes proof status without adding a planted-defect detection. The
fixed-code alarm count fell by one, but alarms appeared in one more
specimen. The same adjudications left 47 buggy/fixed findings unreviewed
(24 buggy, 23 fixed), so the new totals are the runner's scores, not a
fresh human adjudication.
The first worksheet pass also reported 22 unmatched prior reviews under the
former mode-local staleness rule; 21 of those rulings were still used by the
with-LLM audit. Because `finding_reviews` is shared across modes, staleness
now means unused in all available audit modes, leaving one genuinely stale
review for the same remeasurement. The run does not isolate those changes to
a single upstream PR. [`specimens/ADJUDICATION_WORKSHEET.md`](../specimens/ADJUDICATION_WORKSHEET.md)
organizes those decisions for human review: it was regenerated on 2026-11-26
at the same Core/Agent commits, reproduced the same 24 buggy-code and 23
fixed-code unreviewed findings, and groups them into the same review
workflow. Fixed-variant entries link both the buggy source and `fixed.patch`.

To reproduce, use a disposable checkout of the pinned Demo revision
and sibling Core and Agent checkouts. With no LLM credentials in the
environment or Agent's `.env`, run:

```sh
python3 scripts/run_specimen_audits.py --mumei-bin ../mumei/target/debug/mumei
```

This rewrites the checkout's audit and scoreboard outputs. Regenerate the
human-review worksheet in that checkout with
`python3 scripts/extract_adjudication_worksheet.py`. The LLM baseline used
`openai/gpt-6-luna` via OpenRouter, which was unavailable for this rerun. The
local `qwen2.5-coder:1.5b` pilot timed out after 120 seconds on the first
specimen's JSON audit; it did not yield a comparable score.

## Roadmap snapshot

This is the before/after measurement for
[roadmap item 5](https://github.com/mumei-lang/mumei/issues/1448).

- Core [#1466](https://github.com/mumei-lang/mumei/pull/1466) adds an
  `evidence_fingerprint` to successful object acceptance descriptors. Core
  already required canonical linker argument reproduction. Lane B keeps
  the same criterion: it invokes Core directly against a fresh bundle and
  passes the expected build ID. It does not submit an agent evidence-check
  attempt with an independently pinned fingerprint, so it does not score
  `attempt_bound`. The presence of a fingerprint is not proof of attempt
  binding or descriptor authenticity.
- Core [#1467](https://github.com/mumei-lang/mumei/pull/1467) adds offline
  CPU differential tests of the lifter, not a new acceptance path. The
  differential tests are a separate check, not part of the Lane B numerator.
- Demo [#199](https://github.com/mumei-lang/mumei-demo/pull/199) adds
  [port-divergence replay and risky-operation lint](../proofs/PORT_DIVERGENCE.md).
  Replay of the recorded LLM ports reproduced 26 divergences across 12 cases;
  it does not change the hand-written reference ports or measure fresh model
  output.
- Agent [#1343](https://github.com/mumei-lang/mumei-agent/pull/1343) can now
  refute supported Python bodies that violate extracted postconditions
  instead of treating the extracted contract alone as proof of the body.
  Demo [#201](https://github.com/mumei-lang/mumei-demo/pull/201) updates the
  expected audit scenario outcomes; it does not change the specimen corpus
  or scoring rules.
