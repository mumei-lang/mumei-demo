# Fixed single-record execution experiment

This is a limited, single-process adapter for a record-operation proposal. The
proposal is data, not executable code. It addresses the gap between checking a
request and actually updating the current record: one host-owned lock encloses
parsing, authorization, version comparison, staging and publication. It is not
a backend framework, database service or sandbox for Python programs.

## Run without credentials or extra dependencies

```bash
printf '%s\n' '{"target":1,"expected_version":3,"operation":"update","field":"value","value":50}' \
  | python3 scripts/record_execution.py
printf '%s\n' '{"target":1,"expected_version":3,"operation":"read"}' \
  | python3 scripts/record_execution.py
make test-record-execution
```

The CLI uses fixed demo inputs: principal `(organization=7, user=10,
role=writer)`, target `1`, record `(organization=7, owner=10, version=3,
value=40)`, and policy revision `1` with both operations enabled. Each process
starts fresh; separate CLI invocations do **not** share records or prevent
replay across restarts. Exit `0` means accepted, `1` means rejected. Standard
output is one JSON outcome; malformed UTF-8, oversized input and malformed JSON
are rejection outcomes rather than successful empty runs.

For multiple requests, a trusted host constructs one `RecordExecutor`, retains
it, and calls `execute(principal, json_text)` for each request. The proposer
supplies only the JSON text; it receives neither this instance, principal,
records, policy, callbacks, nor credentials. Principal selection is a separate
host input, not a proposal field. The demo does not implement or prove real
authentication or validate whether the caller's asserted role is current.

## Closed input contract

| Operation | Exact JSON keys |
| --- | --- |
| Read | `target`, `expected_version`, `operation: "read"` |
| Update | `target`, `expected_version`, `operation: "update"`, `field: "value"`, `value` |

All keys are required and extra/duplicate keys are rejected, including keys
that purport to select a principal, role, policy, endpoint, path, function,
query, token or code. There is no `eval`, dynamic import, SQL, shell command,
user-supplied callback or external-operation dispatch. The parser accepts only
UTF-8 JSON strings of at most 4096 bytes. Top-level non-objects, nonfinite
numbers, fractional numbers, booleans used as integers and coercions fail closed.

Identifiers, revisions and expected versions are integers from `0` through
`2^63 - 1`; zero is an ordinary identifier. Values range from `-2^63` through
`2^63 - 1`. An update at the maximum version rejects instead of wrapping;
reads at that version still work. These parser/machine limits are deliberately
narrower than the mathematical naturals/integers in the Lean model.

## Current-state execution

- Reads require a known reader/writer/administrator role, matching organization,
  enabled reads and the current version. They return only the record value and
  do not change records. Repeated reads are allowed.
- Updates require matching organization and either an owner writer or an
  administrator, enabled updates and the current version. An administrator
  never crosses organizations. Only value changes; the executor increments the
  version even for an unchanged value. Ownership/organization changes are not
  accepted operations.
- Missing records and failed authority checks return `not_allowed`; missing
  policy returns `missing_policy`. Unauthorized operations return no value.
  There is no permissive configuration fallback.
- The record is looked up and checked inside the same lock used for publication;
  no earlier permission result or caller-constructed snapshot authorizes work.
  Concurrent same-version updates have at most one winner. Subsequent requests
  use the new version; unrelated records are preserved.
- `configure_policy` is a **trusted host-only** operation using the same lock,
  not a JSON operation. Non-missing policy revisions must strictly increase,
  even after policy removal. Restore a policy by assigning a new revision,
  never by reinstalling an old one. This is configuration freshness, not
  delegated authority, revocation tokens or a proof of business-policy quality.

Initial records are copied and typed records/principals/policies are frozen.
Execution stages replacements, outcome and audit metadata before one state
publication; rejection and caught staging/publication errors leave records
unchanged. Exceptions are reported as `internal_error`, without exception
messages or raw proposals. The trusted observer may call `audit_events()`;
each event contains actor/target identifiers, operation, decision, changed
field names, expected/before/after versions and policy revision. Neither read
results nor proposed/stored values, raw inputs, credentials or exception text
enter that metadata. Audit metadata is for the trusted observer, not a public
client response; it can disclose identifiers and record existence/versions.

The outcome also carries its audit event. If in-memory event publication itself
fails, the request rejects without a record change, but the event may exist
only in that returned outcome, not the stored trace. Persistent audit delivery,
memory exhaustion, process termination and crash recovery are not guaranteed.
The retained trace is unbounded in this small finite experiment, not a
production retention policy. Locking is per executor instance, not cross-process.

## Evidence and limits

`tests/test_record_execution.py` exercises the actual parser, executor and CLI,
not recorded fixtures or a permissive substitute. Its 128-case decision matrix
is `4 roles × 2 organizations × 2 users × 2 read flags × 2 update flags × 2
operations`. Other tests cover normal updates/reads, protected or injected
fields, input/type/range boundaries, missing state, policy changes, stale and
repeated updates, concurrency, faults before publication, and minimal audit
disclosure. The dedicated CI job retains the JUnit results and fails on test
failure; branch-protection settings are managed separately.

These are **finite implementation observations**, not formal proof of Python.
The independent model in `mumei-lean/MumeiLean/AuthorizationModel.lean` proves
properties of its own definitions, not this lock, JSON decoder or host process.
The intended policies align, but parsing, bounded arithmetic, policy management,
failure reporting and mutable Python state still need an explicit semantic
correspondence argument before any formal connection can be claimed. No
`lean_verified`, G5, Claim Book or Charter result is produced by this adapter.

Trusted boundaries remain: host-selected principal, initial state and policy,
the Python runtime, and correct exclusive use of this instance. Python callers
can access internals or modify the module; underscore names and frozen data
classes do not stop arbitrary same-process code. Real authentication, production
storage, networking, distributed transactions, dynamic delegation, external
delivery and deployment safety are out of scope. The optional
[`make demo-record-execution`](../scenarios/record_execution_demo/README.md)
connects `.mm` local contracts, independent model evidence, finite observations
and negative controls through the existing evidence display without conflating
them. It requires Lean separately; the adapter and its standalone tests do not.
