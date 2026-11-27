#!/usr/bin/env python3
"""Small shared wrapper around `mumei verify --json`."""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

REFUTATION = re.compile(r"^Verification Error: (Postcondition|Call to \S+: precondition|Potential |"
                        r"(Loop )?[Ii]nvariant|[Tt]ermination|[Dd]ecreases)")


def classify(doc: dict | None, returncode: int) -> dict:
    """proven / refuted / inconclusive from `mumei verify --json` output."""
    if doc is None:
        return {"outcome": "inconclusive", "status": f"no-json (exit {returncode})",
                "failure_kind": "environment_failure", "diagnostics": []}
    status = str(doc.get("status", ""))
    diags = [{"atom": d.get("atom", ""), "code": d.get("code", ""),
              "message": str(d.get("message", ""))[:300]}
             for d in doc.get("diagnostics", []) if d.get("severity", "error") == "error"]
    if status == "success" and returncode == 0:
        outcome = "proven"
    elif status == "failed" and int(doc.get("unverifiable", 0) or 0) == 0 and int(doc.get("infra_errors", 0) or 0) == 0:
        # Only a verification failure refutes; an unknown function or a type error says nothing about the code.
        outcome = "refuted" if diags and all(REFUTATION.search(d["message"]) for d in diags) else "inconclusive"
    else:
        outcome = "inconclusive"
    out = {"outcome": outcome, "status": status, "diagnostics": diags}
    if outcome == "inconclusive":
        if int(doc.get("infra_errors", 0) or 0):
            kind = "environment_failure"
        elif int(doc.get("unverifiable", 0) or 0) or status == "input_error" or any(
                d.get("code") == "input_error" or "Unknown function" in d.get("message", "") for d in diags):
            kind = "unsupported"
        else:
            kind = "inconclusive"
        out["failure_kind"] = kind
    return out


def verify_text(mumei_bin: str, text: str, timeout: int) -> dict:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="contract-bench-") as tmp:
        path = Path(tmp) / "case.mm"
        path.write_text(text)
        try:
            proc = subprocess.run([mumei_bin, "verify", "--json", path.name], cwd=tmp,
                                  capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"outcome": "inconclusive", "status": "timeout",
                    "failure_kind": "budget_exhausted", "diagnostics": [],
                    "seconds": round(time.monotonic() - started, 3),
                    "budget_seconds": timeout}
        except OSError as error:
            return {"outcome": "inconclusive", "status": f"verifier startup failed ({type(error).__name__})",
                    "failure_kind": "environment_failure", "diagnostics": [],
                    "seconds": round(time.monotonic() - started, 3),
                    "budget_seconds": timeout}
        try:
            doc = json.loads(proc.stdout[proc.stdout.index("{"):]) if "{" in proc.stdout else None
        except json.JSONDecodeError:
            doc = None
        return {**classify(doc, proc.returncode),
                "seconds": round(time.monotonic() - started, 3),
                "budget_seconds": timeout}

