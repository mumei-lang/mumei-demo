"""Scenario-scoped evidence snapshots; not an application safety grade."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCHEMA = "mumei-demo.scenario-evidence/v1"
GRADES = ("G0", "G1", "G2", "G3", "G4", "G5")
SUCCESS = {"PASS", "REJECTED", "CERTIFIED"}


class EvidenceError(ValueError):
    pass


def _object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError("duplicate JSON key")
        result[key] = value
    return result


def _json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_object)
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise EvidenceError("missing or invalid JSON artifact") from None
    if not isinstance(value, dict):
        raise EvidenceError("artifact must contain an object")
    return value


def _path(root: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or Path(name).is_absolute() or ".." in Path(name).parts:
        raise EvidenceError("artifact path must be relative to the report directory")
    path = root.resolve() / name
    try:
        if not path.resolve().is_relative_to(root.resolve()):
            raise EvidenceError("artifact path escapes the report directory")
    except (OSError, ValueError, RuntimeError):
        raise EvidenceError("invalid artifact path") from None
    return path


def _relative(root: Path, name: str) -> str:
    try:
        return Path(name).resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, TypeError):
        raise EvidenceError("source must be inside the report directory") from None


def _digest(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        raise EvidenceError("missing or unreadable artifact") from None


def _strings(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def _unique(rows: list[dict], key: str) -> dict:
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get(key), str) or not row[key]:
            raise EvidenceError(f"missing {key} identifier")
        if row[key] in result:
            raise EvidenceError(f"duplicate {key} identifier: {row[key]}")
        result[row[key]] = row
    return result


def capture_identities(data: dict, root: Path) -> dict:
    """Bind only declared evidence files, without copying their contents."""
    config = data.get("evidence_requirements")
    if not isinstance(config, dict) or not _strings(config.get("artifacts", [])):
        return {}
    names = set(config.get("artifacts", []))
    for entry in data.get("claim_book", {}).get("entries", []):
        for name in (entry.get("file"), entry.get("cert")):
            if isinstance(name, str):
                names.add(name)
        if entry.get("source"):
            try:
                names.add(_relative(root, entry["source"]))
            except EvidenceError:
                pass
    for layer in data.get("layers", {}).values():
        for step in layer.get("steps", []):
            if step.get("output_file"):
                names.add(step["output_file"])
    identities = {}
    for name in sorted(names):
        try:
            identities[name] = _digest(_path(root, name))
        except EvidenceError:
            continue
    return identities


def _checked_path(data: dict, root: Path, name: str) -> Path:
    path = _path(root, name)
    if data.get("evidence_identities", {}).get(name) != _digest(path):
        raise EvidenceError(f"artifact identity is missing or changed: {name}")
    return path


def _claim_book(data: dict, root: Path, entry: dict, source: str) -> tuple[dict, dict]:
    if entry.get("status") != "ok":
        raise EvidenceError("Claim Book collection was not successful")
    if _relative(root, entry.get("source")) != source:
        raise EvidenceError("Claim Book source does not match the required source")
    source_path = _checked_path(data, root, source)
    certificate = _checked_path(data, root, entry.get("cert"))
    report = _checked_path(data, root, entry.get("file"))
    book = _json(report)
    cert = _json(certificate)
    if book.get("schema") != "mumei.claimbook/v1":
        raise EvidenceError("unsupported Claim Book schema")
    if cert.get("version") != "1.1":
        raise EvidenceError("unsupported certificate version")
    if book.get("certificate_integrity") != "match":
        raise EvidenceError("certificate integrity is not match")
    if book.get("input") != str(source_path) or book.get("certificate") != str(certificate):
        raise EvidenceError("Claim Book input or certificate identity does not match")
    claims = book.get("claims")
    if not isinstance(claims, list) or not claims:
        raise EvidenceError("Claim Book has no claims")
    indexed = _unique(claims, "atom")
    if not isinstance(book.get("generator"), dict) or not isinstance(book.get("trusted_base"), dict):
        raise EvidenceError("generator or trusted base is unavailable")
    for claim in claims:
        if (
            claim.get("effective_grade") not in GRADES
            or claim.get("freshness") not in {"fresh", "drifted", "uncertified"}
            or not isinstance(claim.get("effective_grade_complete"), bool)
            or not all(isinstance(claim.get(key), str) for key in ("requires", "ensures", "evidence_kind"))
            or not all(_strings(claim.get(key)) for key in ("dependencies", "unresolved_dependencies", "assumed_clauses"))
        ):
            raise EvidenceError("invalid claim evidence fields")
        discrimination = claim.get("discrimination")
        if discrimination is not None:
            keys = ("tested", "killed", "survived", "unanalyzable")
            if (not isinstance(discrimination, dict)
                or discrimination.get("status") not in {"discriminating", "weak", "inconclusive", "no_mutants", "not_checked"}
                or not all(type(discrimination.get(key)) is int and discrimination[key] >= 0 for key in keys)
                or discrimination["tested"] != sum(discrimination[key] for key in keys[1:])
                or not _strings(discrimination.get("surviving"))
                or len(discrimination["surviving"]) != discrimination["survived"]):
                raise EvidenceError("invalid discrimination evidence")
        observation = claim.get("observation")
        if observation is not None and (not isinstance(observation, dict)
            or observation.get("status") not in {"supported", "contradicted", "inconclusive", "not_observed"}
            or not all(type(observation.get(key)) is int and observation[key] >= 0 for key in ("supporting", "contradicting", "neutral"))):
            raise EvidenceError("invalid observation evidence")
    summary = book.get("summary", {})
    if type(summary.get("total")) is not int or summary["total"] != len(claims):
        raise EvidenceError("Claim Book claim count does not match")
    for field, key, values in (("by_effective_grade", "effective_grade", GRADES), ("by_freshness", "freshness", ("fresh", "drifted", "uncertified"))):
        counts = summary.get(field, {})
        if not isinstance(counts, dict) or any(type(counts.get(value)) is not int or counts[value] != sum(claim[key] == value for claim in claims) for value in values):
            raise EvidenceError("Claim Book summary does not match its claims")
    return book, indexed


def _coverage(claims: dict, atom: str) -> dict:
    pending, visited, missing, incomplete = [atom], set(), set(), set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        claim = claims.get(name)
        if claim is None:
            missing.add(name)
            continue
        if not claim["effective_grade_complete"]:
            incomplete.add(name)
        missing.update(claim["unresolved_dependencies"])
        pending.extend(claim["dependencies"])
    direct = set(claims[atom]["unresolved_dependencies"]) | (set(claims[atom]["dependencies"]) - claims.keys())
    return {
        "complete": not missing and not incomplete,
        "reachable": sorted(visited - missing),
        "unresolved_dependencies": sorted(missing),
        "direct_unresolved_dependencies": sorted(direct),
        "transitive_unresolved_dependencies": sorted(missing - direct),
        "incomplete_dependencies": sorted(incomplete - {atom}),
        "incomplete_claims": sorted(incomplete),
    }


def aggregate_evidence(data: dict, root: Path) -> dict:
    identities = data.get("evidence_identities", {})
    summary = {
        "schema": SCHEMA,
        "scenario": data.get("scenario"),
        "version": data.get("version"),
        "status": "incomplete",
        "claims": [],
        "execution_observations": [],
        "declared_assumptions": [],
        "reported_trusted_base": [],
        "unverified_connections": [],
        "out_of_scope": [],
        "issues": [],
        "identities": dict(sorted(identities.items())) if isinstance(identities, dict) and all(isinstance(key, str) and isinstance(value, str) for key, value in identities.items()) else {},
    }
    issues = summary["issues"]
    try:
        config = data.get("evidence_requirements")
        allowed = {"claims", "steps", "charter_steps", "artifacts", "declared_assumptions", "unverified_connections", "out_of_scope"}
        if not isinstance(config, dict) or set(config) - allowed:
            raise EvidenceError("invalid evidence requirements")
        stages = config.get("steps")
        if not isinstance(config.get("claims"), list) or not config["claims"] or not isinstance(stages, dict) or not stages or not all(isinstance(key, str) and key and isinstance(value, str) and value for key, value in stages.items()):
            raise EvidenceError("non-empty required claims and steps must be declared")
        if not isinstance(identities, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in identities.items()):
            raise EvidenceError("invalid artifact identities")
        if not _strings(config.get("charter_steps", [])) or not set(config.get("charter_steps", [])) <= set(config["steps"]):
            raise EvidenceError("Charter steps must reference required steps")
        summary["requirements_sha256"] = hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if not _strings(config.get("artifacts", [])):
            raise EvidenceError("artifacts must be relative path strings")
        for name in sorted(config.get("artifacts", [])):
            try:
                _checked_path(data, root, name)
            except EvidenceError as error:
                issues.append(str(error))
        for key in ("declared_assumptions", "unverified_connections", "out_of_scope"):
            if not _strings(config.get(key, [])):
                raise EvidenceError(f"{key} must be an array of descriptions")
            summary[key] = list(config.get(key, []))
        steps = _unique([step for layer in data.get("layers", {}).values() for step in layer.get("steps", [])], "id")
        books = _unique(data.get("claim_book", {}).get("entries", []), "step")
        charter = _unique(data.get("charter_gate", {}).get("entries", []), "step")
        for step_id in sorted(set(config["steps"])):
            step = steps.get(step_id, {})
            observation = {"step": step_id, "stage": step.get("harness_stage"), "status": step.get("status", "unavailable")}
            summary["execution_observations"].append(observation)
            if step.get("harness_stage") != stages[step_id]:
                issues.append(f"required harness stage does not match: {step_id}")
            if step.get("status") not in SUCCESS:
                issues.append(f"required step is not successful: {step_id}")
                continue
            try:
                _checked_path(data, root, step.get("output_file"))
            except EvidenceError as error:
                issues.append(f"{step_id}: {error}")
            if step_id in config.get("charter_steps", []):
                gate = charter.get(step_id, {})
                observation["charter"] = {key: gate.get(key) for key in ("gate_status", "lock_status", "atoms")}
                expected = "fail" if step.get("expect_failure") else "pass"
                if gate.get("status") != "ok" or gate.get("gate_status") != expected:
                    issues.append(f"required Charter result does not match: {step_id}")
                if not isinstance(gate.get("atoms"), list) or not gate["atoms"]:
                    issues.append(f"required Charter atoms are unavailable: {step_id}")
                else:
                    _unique(gate["atoms"], "name")
        seen = set()
        for requirement in config["claims"]:
            try:
                if not isinstance(requirement, dict) or set(requirement) - {"step", "source", "atom", "minimum_grade", "require_complete", "require_discriminating"}:
                    raise EvidenceError("invalid required claim selector")
                if not all(isinstance(requirement.get(key), str) and requirement[key] for key in ("step", "source", "atom")):
                    raise EvidenceError("required claim needs exact step, source, and atom")
                step_id, source, name = (requirement[key] for key in ("step", "source", "atom"))
                selector = (step_id, source, name)
                if selector in seen:
                    raise EvidenceError("duplicate required claim selector")
                seen.add(selector)
                if step_id not in config["steps"] or steps.get(step_id, {}).get("status") != "PASS":
                    raise EvidenceError("required claim step is missing or not PASS")
                minimum = requirement.get("minimum_grade")
                if minimum not in GRADES or not all(isinstance(requirement.get(key, False), bool) for key in ("require_complete", "require_discriminating")):
                    raise EvidenceError("invalid claim gate requirements")
                book, claims = _claim_book(data, root, books.get(step_id, {}), source)
                if name not in claims:
                    raise EvidenceError("required fully qualified claim was not found")
                claim = claims[name]
                coverage = _coverage(claims, name)
                problems = []
                if any(claims[dependency]["freshness"] != "fresh" for dependency in coverage["reachable"]):
                    problems.append("claim or dependency evidence is not fresh")
                if GRADES.index(claim["effective_grade"]) < GRADES.index(minimum):
                    problems.append("effective grade is below the requirement")
                if any(GRADES.index(claims[dependency]["effective_grade"]) < GRADES.index(minimum) for dependency in coverage["reachable"] if dependency != name):
                    problems.append("dependency grade is below the requirement")
                if requirement.get("require_complete") and not coverage["complete"]:
                    problems.append("dependency coverage is incomplete")
                discrimination = claim.get("discrimination")
                if requirement.get("require_discriminating") and (not isinstance(discrimination, dict) or discrimination.get("status") != "discriminating" or discrimination["tested"] == 0 or discrimination["killed"] != discrimination["tested"]):
                    problems.append("discriminating controls are missing or insufficient")
                observation = claim.get("observation")
                if isinstance(observation, dict) and (observation.get("contradicting", 0) != 0 or observation.get("status") == "contradicted"):
                    problems.append("observations contradict the contract")
                summary["claims"].append({
                    "step": step_id, "source": source, "atom": name,
                    "status": "satisfied" if not problems else "incomplete",
                    "minimum_grade": minimum,
                    **{key: claim.get(key) for key in ("effective_grade", "evidence_kind", "freshness", "requires", "ensures", "content_hash", "proof_hash")},
                    "dependency_coverage": coverage,
                    "assumed_clauses": {dependency: claims[dependency]["assumed_clauses"] for dependency in coverage["reachable"] if claims[dependency]["assumed_clauses"]},
                    "discrimination": discrimination or {"status": "unavailable"},
                    "observation": observation or {"status": "unavailable"},
                    "generator": book.get("generator", {}),
                    "certificate": {"file": books[step_id]["cert"], "version": "1.1"},
                    "next_steps": "Inspect the existing Claim Book report for verifier recommendations.",
                    "certificate_integrity": book["certificate_integrity"],
                    "issues": problems,
                })
                summary["reported_trusted_base"].append({"step": step_id, "source": source, "trusted_base": book.get("trusted_base", {})})
                issues.extend(f"{source}::{name}: {problem}" for problem in problems)
            except EvidenceError as error:
                issues.append(str(error))
    except (EvidenceError, AttributeError, TypeError, KeyError) as error:
        issues.append(str(error) if isinstance(error, EvidenceError) else "invalid evidence structure")
    summary["claims"].sort(key=lambda row: (row["source"], row["atom"], row["step"]))
    summary["reported_trusted_base"].sort(key=lambda row: (row["source"], row["step"]))
    summary["issues"] = sorted(set(issues))
    if not summary["issues"]:
        summary["status"] = "satisfied"
    return summary


def load_result(path: Path) -> dict:
    data = _json(path)
    if any(key in data for key in ("evidence_requirements", "evidence_identities", "evidence_summary")):
        data["evidence_summary"] = aggregate_evidence(data, path.parent)
        if data["evidence_summary"]["status"] != "satisfied":
            data["overall_status"] = "FAIL"
    return data


def render_evidence(data: dict) -> str:
    summary = data.get("evidence_summary")
    if not isinstance(summary, dict):
        return ""
    def cell(value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")
    lines = ["## Scenario Evidence", "", f"Required evidence: **{summary['status']}** (not an application safety grade).",
             f"Scenario: {cell(summary.get('scenario'))}; version: {cell(summary.get('version'))}; requirements SHA-256: {cell(summary.get('requirements_sha256', 'unavailable'))}", "",
             "| Source / claim | Evidence | Effective grade | Freshness | Dependency coverage | Controls | Observations |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for claim in summary["claims"]:
        lines.append("| " + " | ".join(cell(value) for value in (
            f"{claim['source']} :: {claim['atom']}", claim["evidence_kind"], claim["effective_grade"], claim["freshness"],
            "complete" if claim["dependency_coverage"]["complete"] else "incomplete",
            claim["discrimination"]["status"], claim["observation"]["status"],
        )) + " |")
    for claim in summary["claims"]:
        lines.extend(["", f"### {cell(claim['source'])} :: {cell(claim['atom'])}",
                      f"- Requires: {cell(claim['requires'])}", f"- Ensures: {cell(claim['ensures'])}",
                      f"- Dependency details: {cell(json.dumps(claim['dependency_coverage'], sort_keys=True))}",
                      f"- Controls: {cell(json.dumps(claim['discrimination'], sort_keys=True))}",
                      f"- Finite observations (not proof): {cell(json.dumps(claim['observation'], sort_keys=True))}",
                      f"- Assumed clauses: {cell(json.dumps(claim['assumed_clauses'], sort_keys=True))}",
                      f"- Generator: {cell(json.dumps(claim['generator'], sort_keys=True))}",
                      f"- Certificate: {cell(json.dumps(claim['certificate'], sort_keys=True))}; integrity: {cell(claim['certificate_integrity'])}",
                      f"- Content / proof hashes: {cell(claim['content_hash'])} / {cell(claim['proof_hash'])}"])
    lines.extend(["", "### Execution observations (not formal proof)"])
    lines.extend(f"- {cell(row['step'])} / {cell(row['stage'])}: {cell(row['status'])}" + (f"; Charter: {cell(json.dumps(row['charter'], sort_keys=True))}" if "charter" in row else "") for row in summary["execution_observations"])
    for key, title in (("declared_assumptions", "Declared assumptions (not checked facts)"),
                       ("reported_trusted_base", "Trusted base reported by the verifier"),
                       ("unverified_connections", "Unverified connections"), ("out_of_scope", "Out of scope"),
                       ("issues", "Missing or conflicting evidence")):
        lines.extend(["", f"### {title}"])
        lines.extend(f"- {cell(json.dumps(item, sort_keys=True) if isinstance(item, dict) else item)}" for item in summary[key])
        if not summary[key]:
            lines.append("- None reported.")
    lines.extend(["", "### Artifact identities", "", "Hashes bind this local snapshot; they do not establish authenticity, semantic equivalence, or deployment safety."])
    lines.extend(f"- {cell(name)}: {digest}" for name, digest in summary["identities"].items())
    return "\n".join(lines)
