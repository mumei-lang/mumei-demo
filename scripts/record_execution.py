"""Fixed, single-process record operations over JSON data; not a Python sandbox."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, replace
from threading import Lock

MAX_JSON_BYTES = 4096
MAX_NAT = (1 << 63) - 1
MIN_VALUE = -(1 << 63)
MAX_VALUE = MAX_NAT
ROLES = ("reader", "writer", "administrator", "unknown")


def _nat(value: object) -> bool:
    return type(value) is int and 0 <= value <= MAX_NAT


def _integer(value: object) -> bool:
    return type(value) is int and MIN_VALUE <= value <= MAX_VALUE


@dataclass(frozen=True)
class Principal:
    organization: int
    user: int
    role: str


@dataclass(frozen=True)
class Record:
    organization: int
    owner: int
    version: int
    value: int


@dataclass(frozen=True)
class Policy:
    revision: int
    read_enabled: bool
    update_enabled: bool


@dataclass(frozen=True)
class Proposal:
    target: int
    expected_version: int
    operation: str
    value: int | None = None


@dataclass(frozen=True)
class AuditEvent:
    principal: Principal | None
    target: int | None
    operation: str | None
    accepted: bool
    reason: str
    changed_fields: tuple[str, ...]
    expected_version: int | None
    version_before: int | None
    version_after: int | None
    policy_revision: int | None


@dataclass(frozen=True)
class Outcome:
    accepted: bool
    reason: str
    value: int | None
    audit: AuditEvent


@dataclass(frozen=True)
class _State:
    records: dict[int, Record]
    policy: Policy | None
    last_policy_revision: int
    events: tuple[AuditEvent, ...] = ()


def _principal(value: object) -> bool:
    return (type(value) is Principal and _nat(value.organization) and _nat(value.user)
            and type(value.role) is str and value.role in ROLES)


def _policy(value: object) -> bool:
    return (value is None or type(value) is Policy and _nat(value.revision)
            and type(value.read_enabled) is bool and type(value.update_enabled) is bool)


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise ValueError("nonfinite number")


def parse_proposal(payload: str) -> Proposal:
    if type(payload) is not str or len(payload.encode("utf-8")) > MAX_JSON_BYTES:
        raise ValueError("invalid JSON input")
    data = json.loads(payload, object_pairs_hook=_unique_object, parse_constant=_nonfinite)
    if type(data) is not dict or type(data.get("operation")) is not str:
        raise ValueError("invalid proposal")
    operation = data["operation"]
    required = {"target", "expected_version", "operation"}
    if operation == "update":
        required |= {"field", "value"}
        if data.get("field") != "value" or not _integer(data.get("value")):
            raise ValueError("invalid update")
    elif operation != "read":
        raise ValueError("unknown operation")
    if set(data) != required or not _nat(data["target"]) or not _nat(data["expected_version"]):
        raise ValueError("invalid fields")
    return Proposal(data["target"], data["expected_version"], operation, data.get("value"))


class RecordExecutor:
    """Host-owned state. The proposer supplies JSON only, never this instance."""

    def __init__(self, records: dict[int, Record], policy: Policy | None):
        if type(records) is not dict or not _policy(policy):
            raise ValueError("invalid initial state")
        copied = records.copy()
        for target, record in copied.items():
            if (not _nat(target) or type(record) is not Record
                    or not all(_nat(v) for v in (record.organization, record.owner, record.version))
                    or not _integer(record.value)):
                raise ValueError("invalid initial record")
        self._lock = Lock()
        self._state = _State(copied, policy, -1 if policy is None else policy.revision)

    def configure_policy(self, policy: Policy | None) -> None:
        """Trusted host configuration, serialized with record operations."""
        if not _policy(policy):
            raise ValueError("invalid policy")
        with self._lock:
            old = self._state
            if policy is not None and policy.revision <= old.last_policy_revision:
                raise ValueError("policy revision must increase")
            revision = old.last_policy_revision if policy is None else policy.revision
            self._state = _State(old.records, policy, revision, old.events)

    def audit_events(self) -> tuple[AuditEvent, ...]:
        """Metadata for a trusted observer, not a response channel to the proposer."""
        with self._lock:
            return self._state.events

    @staticmethod
    def _evaluate(state: _State, p: Principal, q: Proposal) -> tuple[str, Record | None, int | None]:
        policy, record = state.policy, state.records.get(q.target)
        if policy is None:
            return "missing_policy", None, None
        if record is None or record.organization != p.organization:
            return "not_allowed", None, None
        if q.operation == "read":
            allowed = policy.read_enabled and p.role in ("reader", "writer", "administrator")
        else:
            allowed = policy.update_enabled and (
                p.role == "administrator" or p.role == "writer" and p.user == record.owner
            )
        if not allowed:
            return "not_allowed", None, None
        if q.expected_version != record.version:
            return "version_conflict", None, None
        if q.operation == "read":
            return "accepted", None, record.value
        if record.version == MAX_NAT:
            return "version_exhausted", None, None
        return "accepted", replace(record, value=q.value, version=record.version + 1), None

    @staticmethod
    def _event(state: _State, p: Principal | None, q: Proposal | None, reason: str) -> AuditEvent:
        record = None if q is None else state.records.get(q.target)
        before = None if record is None else record.version
        updated = reason == "accepted" and q is not None and q.operation == "update"
        return AuditEvent(
            p, None if q is None else q.target, None if q is None else q.operation,
            reason == "accepted", reason, ("value",) if updated else (),
            None if q is None else q.expected_version, before,
            before + 1 if updated else before,
            None if state.policy is None else state.policy.revision,
        )

    def execute(self, principal: Principal, payload: str) -> Outcome:
        with self._lock:
            old = self._state
            p, q = None, None
            try:
                changed, value = None, None
                if not _principal(principal):
                    reason = "invalid_principal"
                else:
                    p = principal
                    try:
                        q = parse_proposal(payload)
                    except (ValueError, TypeError, RecursionError):
                        reason = "invalid_proposal"
                    else:
                        reason, changed, value = self._evaluate(old, p, q)
                event = self._event(old, p, q, reason)
                result = Outcome(reason == "accepted", reason, value, event)
                records = old.records
                if changed is not None:
                    records = old.records.copy()
                    records[q.target] = changed
                staged = _State(records, old.policy, old.last_policy_revision, old.events + (event,))
            except Exception:
                event = self._event(old, p, q, "internal_error")
                result = Outcome(False, "internal_error", None, event)
                # Reporting failure must not publish a staged record update.
                try:
                    self._state = _State(old.records, old.policy, old.last_policy_revision,
                                         old.events + (event,))
                except Exception:
                    pass
                return result
            self._state = staged
            return result


def main() -> int:
    """One request against fixed demo state; no real authentication or persistence."""
    executor = RecordExecutor({1: Record(7, 10, 3, 40)}, Policy(1, True, True))
    try:
        payload = sys.stdin.buffer.read(MAX_JSON_BYTES + 1).decode("utf-8")
    except UnicodeError:
        payload = ""
    result = executor.execute(Principal(7, 10, "writer"), payload)
    print(json.dumps(asdict(result), sort_keys=True))
    return 0 if result.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
