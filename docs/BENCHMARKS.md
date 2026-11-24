# Three benchmark lanes

These lanes measure different capabilities. There is no combined score:
proving a contract, accepting a native object, and finding a bug without a
supplied contract are not interchangeable.

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

## Lane B: what passed, and where the rest stopped

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

## Reproduce the live baseline (A and B)

From the demo root with a built Linux x86-64 Mumei CLI and a C linker:

```sh
python3 scripts/run_machine_tv_bench.py --mumei-bin ../mumei/target/debug/mumei
```

The run used demo corpus HEAD `67b59e2812c51428a289687421fa454455826116`
and a fresh build of the Core HEAD above (Mumei 0.6.23, GCC 11.4.0).
It took 43.9 seconds with four workers and a 120-second per-command timeout,
with no model calls. The command prints the Z3-versus-native cross-tab and
writes per-variant outcomes, stages, timings, input hashes and tool
identity to `reports/machine_tv_bench.json`.

The native path appends only a constant, unrelated `main` to satisfy the
bundle entry requirement; the original contract and target atom are unchanged.
It passes the manifest SHA-256 from the freshly built bundle to
`accept-object`. A zero exit, a source proof, or a diagnostic TV recheck
alone is not acceptance: the descriptor must bind that build ID, report
checked source→machine TV and mark the benchmark atom equivalent. The
baseline measures these hand-written ports, not translation from the
original specimen languages, optimized builds across different profiles,
producer authenticity, or runtime behavior.

## Roadmap snapshot

For [roadmap item 5](https://github.com/mumei-lang/mumei/issues/1448), Agent
[#1326](https://github.com/mumei-lang/mumei-agent/pull/1326) had landed in
`develop` at `790b4fd6` (closing #1325), but Lane C's recorded audits
predate it and the A/B port runs do not exercise LLM extraction. The
[#188](https://github.com/mumei-lang/mumei-demo/issues/188) port-divergence
and risky-op checks, Core [#1445](https://github.com/mumei-lang/mumei/issues/1445)
attempt binding, and Core [#1446](https://github.com/mumei-lang/mumei/issues/1446)
lifter CPU differential testing were still open. This run does not measure
their effects.
