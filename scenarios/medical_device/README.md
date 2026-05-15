# Medical Device Control: Insulin Pump Safety

## Overview
This scenario demonstrates mumei's ability to catch dosage control bugs in
medical device software. The buggy implementation skips the safety-check state,
which could lead to insulin overdose.

## Bug
The buggy `deliver_insulin` function performs delivery directly from `Idle`
without first proving the requested dose fits within the remaining hourly
capacity.

## Fix
The corrected implementation adds:
- `requires: current_hour_dosage + requested_dose <= max_dose_per_hour`
- `ensures: result <= max_dose_per_hour - current_hour_dosage`
- an explicit `Idle -> SafetyChecked -> Delivered` state sequence

## Verification
- Z3 verifies the dosage bounds
- Lean proves cumulative dosage safety over time
