from __future__ import annotations

import dataclasses
import itertools
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from threading import Barrier, Event

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import record_execution as runtime
from record_execution import MAX_NAT, MAX_VALUE, MIN_VALUE, Policy, Principal, Record, RecordExecutor

WRITER = Principal(7, 10, "writer")
POLICY = Policy(1, True, True)
RECORD = Record(7, 10, 3, 40)


def request(operation="update", target=1, version=3, value=50, **extra):
    data = {"target": target, "expected_version": version, "operation": operation}
    if operation == "update":
        data.update(field="value", value=value)
    data.update(extra)
    return json.dumps(data)


@pytest.fixture
def executor():
    return RecordExecutor({1: RECORD, 2: Record(8, 11, 4, 90)}, POLICY)


MATRIX = list(itertools.product(
    runtime.ROLES, [7, 8], [10, 11], [False, True], [False, True], ["read", "update"]
))


@pytest.mark.parametrize("role,organization,user,reads,updates,operation", MATRIX)
def test_authority_matrix(role, organization, user, reads, updates, operation):
    executor = RecordExecutor({1: RECORD}, Policy(1, reads, updates))
    allowed_updates = {"reader": set(), "writer": {10}, "administrator": {10, 11}, "unknown": set()}
    allowed_reads = {"reader", "writer", "administrator"}
    expected = organization == 7 and (
        reads and role in allowed_reads if operation == "read" else updates and user in allowed_updates[role]
    )
    result = executor.execute(Principal(organization, user, role), request(operation))
    assert result.accepted is expected
    assert result.value == (40 if expected and operation == "read" else None)
    assert executor._state.records == {
        1: Record(7, 10, 4, 50) if expected and operation == "update" else RECORD
    }
    assert executor._state.policy == Policy(1, reads, updates)
    assert result.audit.accepted is expected


@pytest.mark.parametrize("value", [MIN_VALUE, -1, 0, 40, MAX_VALUE])
def test_update_only_changes_value_and_version(executor, value):
    original_other = executor._state.records[2]
    result = executor.execute(WRITER, request(value=value))
    assert result.accepted
    assert result.value is None
    assert executor._state.records[1] == Record(7, 10, 4, value)
    assert executor._state.records[2] == original_other
    assert result.audit.changed_fields == ("value",)
    assert (result.audit.version_before, result.audit.version_after) == (3, 4)
    assert (result.audit.expected_version, result.audit.policy_revision) == (3, 1)


def test_update_replay_and_next_version(executor):
    assert executor.execute(WRITER, request(value=40)).accepted
    before = executor._state.records.copy()
    repeated = executor.execute(WRITER, request(value=40))
    assert not repeated.accepted and repeated.reason == "version_conflict"
    assert executor._state.records == before
    assert executor.execute(WRITER, request(version=4)).accepted


def test_read_is_repeatable_without_mutation(executor):
    before = executor._state.records.copy()
    for _ in range(3):
        outcome = executor.execute(WRITER, request("read"))
        assert outcome.accepted and outcome.value == 40
        assert outcome.audit.changed_fields == ()
        assert outcome.audit.version_after == outcome.audit.version_before == 3
    assert executor._state.records == before


@pytest.mark.parametrize("version", [0, 2, 4, MAX_NAT])
@pytest.mark.parametrize("operation", ["read", "update"])
def test_current_version_required(executor, version, operation):
    before = executor._state.records.copy()
    result = executor.execute(WRITER, request(operation, version=version))
    assert not result.accepted and result.reason == "version_conflict"
    assert result.value is None
    assert executor._state.records == before


def test_maximum_version_rejects_update_but_allows_read():
    executor = RecordExecutor({0: Record(0, 0, MAX_NAT, MAX_VALUE)}, POLICY)
    actor = Principal(0, 0, "writer")
    result = executor.execute(actor, request(target=0, version=MAX_NAT))
    assert result.reason == "version_exhausted" and not result.accepted
    assert executor._state.records[0].version == MAX_NAT
    assert executor.execute(actor, request("read", target=0, version=MAX_NAT)).value == MAX_VALUE


def test_zero_identifiers_and_initial_version_are_valid():
    executor = RecordExecutor({0: Record(0, 0, 0, 0)}, Policy(0, True, True))
    assert executor.execute(Principal(0, 0, "writer"), request(target=0, version=0)).accepted


INVALID_RAW = [
    "", " ", "null", "[]", "true", "1", '"read"', "{", "{}", "{} {}", "[] trailing",
    '{"operation":"read","operation":"update","target":1,"expected_version":3}',
    '{"operation":"read","target":1,"expected_version":3,"target":1}',
    '{"operation":"update","target":1,"expected_version":3,"field":"value","value":NaN}',
    '{"operation":"update","target":1,"expected_version":3,"field":"value","value":Infinity}',
    "[" * 1100 + "]" * 1100, "\ud800", "x" * (runtime.MAX_JSON_BYTES + 1),
    None, b"{}", {}, [], 3,
]


@pytest.mark.parametrize("payload", INVALID_RAW)
def test_malformed_json_rejects_without_state_change(executor, payload):
    before = executor._state.records.copy()
    result = executor.execute(WRITER, payload)
    assert not result.accepted and result.reason == "invalid_proposal"
    assert result.value is None and result.audit.changed_fields == ()
    assert executor._state.records == before
    assert executor.audit_events()[-1] == result.audit


INVALID_FIELDS = [
    ("operation", "delete"), ("operation", "list"), ("operation", "configure_policy"),
    ("operation", "__import__"), ("operation", "read; DROP TABLE records"),
    ("operation", "eval"), ("operation", ""), ("operation", None), ("operation", {}),
    ("field", "owner"), ("field", "organization"), ("field", "version"),
    ("field", "unknown"), ("field", ["value"]),
] + [(field, value) for field in ("target", "expected_version", "value") for value in
     (True, False, 1.0, "1", None, [], {}, MAX_NAT + 1)] + [
    ("target", -1), ("expected_version", -1), ("value", MIN_VALUE - 1),
]


@pytest.mark.parametrize("field,value", INVALID_FIELDS)
def test_schema_types_operations_and_fields_are_closed(executor, field, value):
    data = json.loads(request())
    data[field] = value
    result = executor.execute(WRITER, json.dumps(data))
    assert not result.accepted and result.reason == "invalid_proposal"
    assert executor._state.records[1] == RECORD


@pytest.mark.parametrize("operation", ["read", "update"])
@pytest.mark.parametrize("field", ["target", "expected_version", "operation", "field", "value"])
def test_missing_or_extraneous_fields_are_not_defaulted(executor, operation, field):
    data = json.loads(request(operation))
    if field in data:
        del data[field]
    else:
        data[field] = "value"
    assert executor.execute(WRITER, json.dumps(data)).reason == "invalid_proposal"
    assert executor._state.records[1] == RECORD


@pytest.mark.parametrize("field", [
    "principal", "organization", "user", "role", "policy", "revision", "function",
    "endpoint", "path", "sql", "shell", "code", "records", "snapshot", "token",
])
def test_proposal_cannot_choose_authority_or_execution_route(executor, field):
    result = executor.execute(WRITER, request(**{field: "private-marker-do-not-log"}))
    assert result.reason == "invalid_proposal"
    assert "private-marker" not in json.dumps(dataclasses.asdict(result))
    assert executor._state.records[1] == RECORD


def test_size_limit_is_bytes_and_not_characters(executor, monkeypatch):
    decode = runtime.json.loads
    called = []

    def tracked(*args, **kwargs):
        called.append(True)
        return decode(*args, **kwargs)

    monkeypatch.setattr(runtime.json, "loads", tracked)
    assert executor.execute(WRITER, "\u00e9" * 2100).reason == "invalid_proposal"
    assert called == []
    padded = request("read")
    assert executor.execute(WRITER, padded + " " * (runtime.MAX_JSON_BYTES - len(padded))).accepted
    assert executor.execute(WRITER, padded + " " * (runtime.MAX_JSON_BYTES - len(padded) + 1)).reason == "invalid_proposal"


def test_matrix_has_independent_read_and_update_flags():
    assert len(MATRIX) == 4 * 2 * 2 * 2 * 2 * 2 == 128
    assert {(case[3], case[4]) for case in MATRIX} == {(False, False), (True, False), (False, True), (True, True)}


def test_model_value_is_not_an_executable_proposal(executor):
    proposal = runtime.Proposal(1, 3, "update", 50)
    assert executor.execute(WRITER, proposal).reason == "invalid_proposal"
    assert executor._state.records[1] == RECORD


def test_policy_revision_at_ceiling_never_wraps():
    executor = RecordExecutor({1: RECORD}, Policy(MAX_NAT, True, True))
    executor.configure_policy(None)
    for policy in [Policy(0, True, True), Policy(MAX_NAT, True, True), Policy(MAX_NAT + 1, True, True)]:
        with pytest.raises(ValueError):
            executor.configure_policy(policy)
    assert executor.execute(WRITER, request()).reason == "missing_policy"


@pytest.mark.parametrize("principal", [
    None, {}, "administrator", Principal(True, 10, "writer"), Principal(7, -1, "writer"),
    Principal(7, 10, "root"), Principal(7, 10, None), Principal(MAX_NAT + 1, 10, "writer"),
])
def test_invalid_principal_is_not_rescued_by_proposal(executor, principal):
    result = executor.execute(principal, request())
    assert result.reason == "invalid_principal" and result.audit.principal is None
    assert not result.accepted and executor._state.records[1] == RECORD


@pytest.mark.parametrize("records,policy", [
    ([], POLICY), ({True: RECORD}, POLICY), ({-1: RECORD}, POLICY),
    ({1: {}}, POLICY), ({1: Record(7, 10, -1, 40)}, POLICY),
    ({1: Record(7, True, 3, 40)}, POLICY), ({1: Record(7, 10, 3, MAX_VALUE + 1)}, POLICY),
    ({1: RECORD}, {}), ({1: RECORD}, Policy(True, True, True)),
    ({1: RECORD}, Policy(1, 1, True)), ({1: RECORD}, Policy(1, True, "yes")),
])
def test_invalid_initial_state_is_not_made_permissive(records, policy):
    with pytest.raises(ValueError):
        RecordExecutor(records, policy)


@pytest.mark.parametrize("records,policy,reason", [
    ({}, POLICY, "not_allowed"), ({1: RECORD}, None, "missing_policy"), ({}, None, "missing_policy"),
])
def test_missing_record_or_configuration_rejects(records, policy, reason):
    executor = RecordExecutor(records, policy)
    result = executor.execute(WRITER, request())
    assert not result.accepted and result.reason == reason
    assert executor._state.records == records


def test_constructor_owns_a_copy_and_results_are_immutable():
    records = {1: RECORD}
    executor = RecordExecutor(records, POLICY)
    records[1] = Record(8, 99, 3, 100)
    assert executor.execute(WRITER, request()).accepted
    event = executor.audit_events()[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.accepted = False
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.principal.role = "administrator"


def test_policy_is_reloaded_and_revisions_cannot_be_restored(executor):
    assert executor.execute(WRITER, request("read")).accepted
    executor.configure_policy(Policy(2, False, False))
    assert executor.execute(WRITER, request()).reason == "not_allowed"
    executor.configure_policy(None)
    assert executor.execute(WRITER, request()).reason == "missing_policy"
    for revision in (0, 1, 2):
        with pytest.raises(ValueError):
            executor.configure_policy(Policy(revision, True, True))
    executor.configure_policy(Policy(3, True, True))
    assert executor.execute(WRITER, request()).accepted
    assert executor.audit_events()[-1].policy_revision == 3


@pytest.mark.parametrize("policy", [{}, False, Policy(-1, True, True), Policy(2, None, True)])
def test_invalid_reconfiguration_keeps_current_policy(executor, policy):
    before = executor._state
    with pytest.raises(ValueError):
        executor.configure_policy(policy)
    assert executor._state is before


def test_same_version_concurrent_updates_have_one_winner(executor):
    count = 24
    barrier = Barrier(count)

    def run(value):
        barrier.wait(timeout=10)
        return executor.execute(WRITER, request(value=value))

    with ThreadPoolExecutor(max_workers=count) as pool:
        outcomes = list(pool.map(run, range(count)))
    assert sum(outcome.accepted for outcome in outcomes) == 1
    assert sum(outcome.reason == "version_conflict" for outcome in outcomes) == count - 1
    assert executor._state.records[1].version == 4
    assert len(executor.audit_events()) == count
    assert sum(event.accepted for event in executor.audit_events()) == 1


def test_independent_targets_are_preserved_under_concurrent_updates():
    count = 16
    executor = RecordExecutor({i: RECORD for i in range(count)}, POLICY)
    barrier = Barrier(count)

    def run(target):
        barrier.wait(timeout=10)
        return executor.execute(WRITER, request(target=target, value=target))

    with ThreadPoolExecutor(max_workers=count) as pool:
        assert all(outcome.accepted for outcome in pool.map(run, range(count)))
    assert executor._state.records == {i: Record(7, 10, 4, i) for i in range(count)}


def test_policy_change_cannot_interleave_decision_and_publication(executor, monkeypatch):
    deciding, release, configuring = Event(), Event(), Event()
    evaluate = executor._evaluate

    def paused(*args):
        outcome = evaluate(*args)
        deciding.set()
        assert release.wait(timeout=10)
        return outcome

    monkeypatch.setattr(executor, "_evaluate", paused)

    def configure():
        configuring.set()
        executor.configure_policy(Policy(2, False, False))

    with ThreadPoolExecutor(max_workers=2) as pool:
        update = pool.submit(executor.execute, WRITER, request())
        assert deciding.wait(timeout=10)
        config = pool.submit(configure)
        assert configuring.wait(timeout=10)
        try:
            with pytest.raises(TimeoutError):
                config.result(timeout=0.05)
        finally:
            release.set()
        assert update.result(timeout=10).accepted
        config.result(timeout=10)
    assert executor.execute(WRITER, request(version=4)).reason == "not_allowed"


def test_stage_exception_does_not_publish_partial_update(executor, monkeypatch, capsys):
    before = executor._state.records.copy()

    def fail(*args, **kwargs):
        raise RuntimeError("private-exception-marker")

    monkeypatch.setattr(runtime, "replace", fail)
    result = executor.execute(WRITER, request())
    assert not result.accepted and result.reason == "internal_error"
    assert executor._state.records == before
    assert executor.audit_events()[-1] == result.audit
    assert result.audit.changed_fields == () and result.value is None
    assert "private-exception-marker" not in json.dumps(dataclasses.asdict(result))
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("all_events_fail", [False, True])
def test_publication_failure_leaves_records_unchanged(executor, monkeypatch, all_events_fail):
    original = runtime._State
    before = executor._state.records.copy()

    def fail(records, *args):
        if records != before or all_events_fail:
            raise RuntimeError("cannot publish event")
        return original(records, *args)

    monkeypatch.setattr(runtime, "_State", fail)
    result = executor.execute(WRITER, request())
    assert not result.accepted and result.reason == "internal_error"
    assert executor._state.records == before
    assert result.audit.version_before == result.audit.version_after == 3
    assert result.audit.changed_fields == ()
    if not all_events_fail:
        assert executor.audit_events()[-1] == result.audit


def test_audit_contains_metadata_not_record_contents_or_proposal_value(executor):
    value = 123456789101112131
    outcome = executor.execute(WRITER, request(value=value))
    assert outcome.accepted
    assert executor.execute(WRITER, request("read", version=4)).value == value
    audit = json.dumps([dataclasses.asdict(event) for event in executor.audit_events()])
    assert str(value) not in audit
    assert '"value":' not in audit
    assert json.loads(audit)[0]["principal"] == dataclasses.asdict(WRITER)


@pytest.mark.parametrize("payload,exit_code,reason", [
    (request(), 0, "accepted"), (request("read"), 0, "accepted"),
    (request(version=2), 1, "version_conflict"), ("", 1, "invalid_proposal"),
    (request(role="administrator"), 1, "invalid_proposal"),
    ("x" * (runtime.MAX_JSON_BYTES + 1), 1, "invalid_proposal"),
])
def test_fixed_cli_uses_json_only(payload, exit_code, reason, monkeypatch):
    monkeypatch.setenv("RECORD_EXECUTION_TEST_SECRET", "not-for-proposal-or-output")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/record_execution.py")],
                            input=payload, text=True, capture_output=True, timeout=10)
    assert result.returncode == exit_code
    assert json.loads(result.stdout)["reason"] == reason
    assert result.stderr == ""
    assert "not-for-proposal-or-output" not in result.stdout


def test_cli_invalid_utf8_is_a_rejection():
    result = subprocess.run([sys.executable, str(ROOT / "scripts/record_execution.py")],
                            input=b"\xff", capture_output=True, timeout=10)
    assert result.returncode == 1
    assert json.loads(result.stdout)["reason"] == "invalid_proposal"
    assert result.stderr == b""
