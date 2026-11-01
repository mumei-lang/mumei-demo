"""Finite record-operation checks and intentionally broken host variants."""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path
from threading import Barrier

from record_execution import Outcome, Policy, Principal, Record, RecordExecutor, _State, parse_proposal

WRITER = Principal(7, 10, "writer")
INITIAL = {1: Record(7, 10, 3, 40), 2: Record(8, 11, 9, 90)}
POLICY = Policy(1, True, True)


def proposal(operation="update", target=1, version=3, **extra):
    data = {"target": target, "expected_version": version, "operation": operation}
    if operation == "update":
        data.update(field="value", value=50)
    data.update(extra)
    return json.dumps(data)


class MissingOrganizationCheck(RecordExecutor):
    @staticmethod
    def _evaluate(state, p, q):
        record = state.records.get(q.target)
        if record is not None:
            p = replace(p, organization=record.organization)
        return RecordExecutor._evaluate(state, p, q)


class MissingOwnershipCheck(RecordExecutor):
    @staticmethod
    def _evaluate(state, p, q):
        record = state.records.get(q.target)
        if record is not None:
            p = replace(p, user=record.owner)
        return RecordExecutor._evaluate(state, p, q)


class ChangedIdentity(RecordExecutor):
    @staticmethod
    def _evaluate(state, p, q):
        reason, changed, value = RecordExecutor._evaluate(state, p, q)
        if changed is not None:
            changed = replace(changed, owner=99)
        return reason, changed, value


class DirectWrite(RecordExecutor):
    def execute(self, principal, payload):
        q = parse_proposal(payload)
        record = self._state.records[q.target]
        event = self._event(self._state, principal, q, "accepted")
        if q.operation == "update":
            records = self._state.records.copy()
            records[q.target] = replace(record, value=q.value, version=record.version + 1)
            self._state = _State(records, self._state.policy, self._state.last_policy_revision,
                                 self._state.events + (event,))
        return Outcome(True, "accepted", record.value if q.operation == "read" else None, event)


VARIANTS = {
    "baseline": RecordExecutor,
    "missing_organization": MissingOrganizationCheck,
    "missing_ownership": MissingOwnershipCheck,
    "changed_identity": ChangedIdentity,
    "direct_write": DirectWrite,
}


def run_checks(factory=RecordExecutor) -> dict:
    rows = []

    def observe(name, principal, payload, reason, expected=None, value=None, setup=None):
        executor = factory(INITIAL, POLICY)
        if setup is not None:
            setup(executor)
        before = executor._state.records.copy()
        policy = executor._state.policy
        try:
            outcome = executor.execute(principal, payload)
            accepted = reason == "accepted"
            passed = (
                outcome.accepted is accepted and outcome.reason == reason and outcome.value == value
                and executor._state.records == (before if expected is None else expected)
                and executor._state.policy == policy
            )
            rows.append({"name": name, "passed": passed, "reason": outcome.reason,
                         "expected_reason": reason, "audit": asdict(outcome.audit)})
        except Exception:
            rows.append({"name": name, "passed": False, "reason": "unexpected_exception",
                         "expected_reason": reason})

    updated = {**INITIAL, 1: Record(7, 10, 4, 50)}
    observe("owner_update", WRITER, proposal(), "accepted", updated)
    observe("administrator_update", Principal(7, 99, "administrator"), proposal(), "accepted", updated)
    observe("reader_read", Principal(7, 99, "reader"), proposal("read"), "accepted", value=40)
    observe("reader_update", Principal(7, 10, "reader"), proposal(), "not_allowed")
    observe("cross_organization", Principal(8, 10, "administrator"), proposal(), "not_allowed")
    observe("wrong_owner", Principal(7, 11, "writer"), proposal(), "not_allowed")
    observe("unknown_role", Principal(7, 10, "unknown"), proposal(), "not_allowed")
    for field in ("organization", "owner", "version", "unknown"):
        observe(f"protected_field_{field}", WRITER, proposal(field=field), "invalid_proposal")
    observe("self_asserted_role", Principal(7, 10, "reader"), proposal(role="administrator"), "invalid_proposal")
    observe("arbitrary_dispatch", WRITER, proposal(operation="eval"), "invalid_proposal")
    observe("target_substitution", WRITER, proposal(target=2, version=9), "not_allowed")
    observe("missing_record", WRITER, proposal(target=42), "not_allowed")
    observe("empty_input", WRITER, "", "invalid_proposal")
    observe("malformed_input", WRITER, "{", "invalid_proposal")
    observe("version_conflict", WRITER, proposal(version=2), "version_conflict")
    observe("replayed_update", WRITER, proposal(), "version_conflict",
            setup=lambda e: e.execute(WRITER, proposal()))
    observe("changed_policy", WRITER, proposal(), "not_allowed",
            setup=lambda e: e.configure_policy(Policy(2, True, False)))
    observe("disabled_read", WRITER, proposal("read"), "not_allowed",
            setup=lambda e: e.configure_policy(Policy(2, False, True)))
    observe("missing_policy", WRITER, proposal(), "missing_policy", setup=lambda e: e.configure_policy(None))
    observe("changed_principal", Principal(7, 10, "reader"), proposal(), "not_allowed",
            setup=lambda e: e.execute(WRITER, proposal("read")))
    observe("old_decision_is_not_input", WRITER, proposal(snapshot={"accepted": True}), "invalid_proposal")

    executor = factory(INITIAL, POLICY)
    barrier = Barrier(2)

    def update(value):
        barrier.wait(timeout=10)
        return executor.execute(WRITER, proposal(value=value))

    concurrent_reason = "checked"
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(update, [50, 60]))
        passed = (sum(o.accepted for o in outcomes) == 1
                  and sum(o.reason == "version_conflict" for o in outcomes) == 1
                  and executor._state.records[1] in (Record(7, 10, 4, 50), Record(7, 10, 4, 60))
                  and executor._state.records[2] == INITIAL[2] and executor._state.policy == POLICY)
    except Exception:
        passed = False
        concurrent_reason = "unexpected_exception"
    rows.append({"name": "concurrent_conflict", "passed": passed, "reason": concurrent_reason})
    failed = [row["name"] for row in rows if not row["passed"]]
    return {"schema": "mumei-demo.record-checks/v1", "status": "passed" if not failed else "failed",
            "cases": rows, "failed_cases": failed, "scope": "finite implementation observations, not proof"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=VARIANTS, default="baseline")
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # Variant selection belongs to the trusted test harness, never proposal JSON.
    report = run_checks(VARIANTS[args.variant])
    report["variant"] = args.variant
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(report, indent=2) + "\n"
        args.output.write_text(encoded, encoding="utf-8")
        if args.output.read_text(encoding="utf-8") != encoded:
            raise ValueError("saved observations do not match")
    except (OSError, ValueError):
        print("Record observation artifact is unavailable or does not match")
        return 2
    print(f"Fixed record checks: {'PASS' if report['status'] == 'passed' else 'FAIL'}")
    for row in report["cases"]:
        if not row["passed"]:
            label = "Unexpected exception in case" if row.get("reason") == "unexpected_exception" else "Violated case"
            print(f"{label}: {row['name']}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
