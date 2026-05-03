# Ownership Transfer Protocol

This scenario demonstrates Mumei's three-layer verification story for a smart
contract ownership-transfer protocol.

## Background

Ownership transfer is a common smart-contract control path: a current owner
proposes a new owner, and the candidate must explicitly accept before privileged
state moves. The safety property is that the contract must never reach
`Transferred` without `accept`.

## L1: Z3 contract verification

The Mumei verifier checks `std/ownership.mm` and emits a proof certificate. The
effect state machine has three states:

- `Idle`: no pending transfer.
- `PendingTransfer`: transfer has been proposed and awaits acceptance.
- `Transferred`: ownership was accepted by the pending owner.

The hostile takeover regression (`tests/test_ownership_error.mm`) attempts to
reach the transferred state from an invalid pre-state. It must be rejected with
`InvalidPreState` / `Temporal effect violation`.

## L2: Agent forge dry run

The agent loads `forge_tasks/vstd_ownership.json` and prints the planned forge
operation without contacting an LLM or mutating the `mumei` repository.

## L3: Lean proof bridge

`MumeiLean.Ownership` contains the finite-state model and the
`no_transfer_without_accept` theorem. The theorem states that accepted ownership
transfer cannot be derived from traces that omit `accept`. When Lake is present,
the scenario builds this module and runs the certificate bridge. Without Lake,
L3 can be skipped while L1 and L2 still pass.

## Expected result

- `verify_pass`: `PASS`, proof certificate generated.
- `verify_reject`: `REJECTED`, hostile takeover rejected as expected.
- `verify_e2e`: `PASS`.
- `forge_dryrun`: `PASS`.
- `lean_build`: `CERTIFIED` when Lake is installed, otherwise `SKIPPED`.
- `lean_bridge`: `PASS` if `verify_pass` completed and its toolchain is
  available.
