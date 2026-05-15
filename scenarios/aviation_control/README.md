# Aviation Control: Runway Allocation Protocol

## Overview
This scenario demonstrates mumei's ability to catch concurrency bugs in
distributed aviation control systems. The buggy implementation skips the
ordered-lock state, which could lead to deadlock.

## Bug
The buggy `allocate_runway` function allocates runways without first proving a
consistent lock order, allowing circular wait conditions between flights.

## Fix
The corrected implementation:
- Enforces `requires: runway1 < runway2` for ordered acquisition
- Uses an explicit `Idle -> Ordered -> Allocated` state sequence
- Acquires resources in priority order

## Verification
- Z3 verifies mutual exclusion
- Agent forge validates the generation task
