# Lean bridge failure regression

Read this when a change touches the Lean bridge / L3 path and you need to confirm a failing `lake` build skips the bridge and fails the demo.

## Lean bridge failure regression

Create a fake failing Lake executable and run the ownership scenario with it first in `PATH`:

```bash
mkdir -p /home/ubuntu/fake-lake
printf '#!/usr/bin/env bash\necho fake lake failure >&2\nexit 42\n' > /home/ubuntu/fake-lake/lake
chmod +x /home/ubuntu/fake-lake/lake
PATH=/home/ubuntu/fake-lake:$PATH MUMEI_BIN=/home/ubuntu/repos/mumei/target/debug/mumei make demo-ownership
```

Expected assertions:

- Command exits non-zero.
- Output includes `l3_lean/lean_build: FAIL`.
- Output includes `l3_lean/lean_bridge: SKIPPED`.
- Output includes `Lean bridge skipped: proof build failed`.
- Output includes `Result: Demo failed. Inspect result.json for details.`.
- After `l3_lean/lean_bridge: SKIPPED`, output must not include `CERTIFIED: no_transfer_without_accept`.
