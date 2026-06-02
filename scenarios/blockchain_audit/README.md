# Blockchain Audit: Smart Contract Vulnerability Suite

Phase 4-6 style scenario for auditing smart-contract code through the Mumei
proof-certificate chain.

The intentionally vulnerable contract demonstrates three audit classes:

- **Reentrancy:** `withdraw` calls out before acquiring `ReentrancyGuard.Locked`.
- **Integer overflow:** `credit_without_overflow_proof` credits a receiver without
  proving the bounded `Uint256` upper limit.
- **Access control:** `transfer_ownership` lacks the `caller == owner`
  authorization precondition.

The corrected contract applies Checks-Effects-Interactions, bounded arithmetic
preconditions, and owner-only transfer contracts. The scenario runs deterministic
L1/Z3 checks, an L2 harness-contract preview, and optional L3/Lean certification
through `MumeiLean.Blockchain`.

Run:

```bash
make demo-blockchain
```

Or invoke the runner directly:

```bash
./scripts/run_blockchain_audit.sh \
  --mumei-repo ../mumei \
  --mumei-lean-repo ../mumei-lean \
  --mumei-agent-repo ../mumei-agent \
  --mumei-bin ../mumei/target/debug/mumei
```
