# P9-G NLAE Integration Demo

This demo connects the four NLAE components:

| Repo | NLAE role | Demo responsibility |
| --- | --- | --- |
| `mumei-agent` | Module A (AV) | Runs `NLAEPipeline` and routes Loss Vector feedback into self-correction |
| `mumei` | Module B (AR) | Provides `examples/nlae_integration_demo.mm`, an intentionally failing vault contract |
| `mumei-lean` | Fidelity Checker | Supplies Lean known witnesses for the repaired vault atom |
| `mumei-demo` | Evaluation Loop | Hosts this reproducible harness and expected output |

## Run

From `mumei-demo`:

```bash
./demos/nlae_integration/run_demo.sh
```

Optional repo overrides:

```bash
MUMEI_REPO=../mumei \
MUMEI_AGENT_REPO=../mumei-agent \
MUMEI_LEAN_REPO=../mumei-lean \
./demos/nlae_integration/run_demo.sh
```

The harness is deterministic: it uses fixture clients to prove the integration path without requiring live LLM credentials or a live Lean build. If a local `mumei` binary is available, it also captures the live `--emit loss-vector` output for inspection.
