# Charter Gate: Reviewed Dosage Contract

This scenario demonstrates how mumei keeps an implementation aligned with a
reviewed contract. The charter gate rejects a repair that weakens an
a postcondition, one that narrows the accepted inputs, and one whose proof relies
on a trusted shortcut below the required Seal Grade. It also reports when the
charter text has changed since its lock was written.

The scenario copies its project into the run's output directory before writing
the charter lock or running checks. Its source project remains unchanged.

## Run

```bash
make demo-charter
```

The `result.json` report records each charter check under `charter_gate`,
including the gate and lock statuses and per-atom findings. The Markdown report
renders those entries in a Charter Gate section.
