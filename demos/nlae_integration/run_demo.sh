#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
MUMEI_REPO=${MUMEI_REPO:-"$REPO_ROOT/../mumei"}
MUMEI_AGENT_REPO=${MUMEI_AGENT_REPO:-"$REPO_ROOT/../mumei-agent"}
MUMEI_LEAN_REPO=${MUMEI_LEAN_REPO:-"$REPO_ROOT/../mumei-lean"}
WORK_DIR=${WORK_DIR:-"$SCRIPT_DIR/.work"}
RESULT_JSON=${RESULT_JSON:-"$WORK_DIR/result.json"}
LOSS_VECTOR_JSON=${LOSS_VECTOR_JSON:-"$WORK_DIR/loss-vector.json"}

mkdir -p "$WORK_DIR"

DEMO_MM="$MUMEI_REPO/examples/nlae_integration_demo.mm"
if [[ ! -f "$DEMO_MM" ]]; then
  echo "missing mumei demo fixture: $DEMO_MM" >&2
  exit 1
fi
if [[ ! -f "$MUMEI_AGENT_REPO/agent/nlae_pipeline.py" ]]; then
  echo "missing mumei-agent pipeline: $MUMEI_AGENT_REPO/agent/nlae_pipeline.py" >&2
  exit 1
fi
if [[ ! -f "$MUMEI_LEAN_REPO/scripts/known_witnesses.py" ]]; then
  echo "missing mumei-lean witnesses: $MUMEI_LEAN_REPO/scripts/known_witnesses.py" >&2
  exit 1
fi

MUMEI_BIN=${MUMEI_BIN:-"$MUMEI_REPO/target/debug/mumei"}
if [[ -x "$MUMEI_BIN" ]]; then
  (
    cd "$WORK_DIR"
    "$MUMEI_BIN" verify --emit loss-vector "$DEMO_MM" >"$LOSS_VECTOR_JSON" 2>"$WORK_DIR/mumei-verify.stderr" || true
  )
fi

PYTHON_CMD=(python3)
if command -v uv >/dev/null 2>&1; then
  PYTHON_CMD=(uv run python)
fi

(
  cd "$MUMEI_AGENT_REPO"
  PYTHONPATH="$MUMEI_AGENT_REPO" "${PYTHON_CMD[@]}" - "$DEMO_MM" "$MUMEI_LEAN_REPO" "$WORK_DIR" "$RESULT_JSON" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

from agent.nlae_pipeline import NLAEPipeline

demo_mm = Path(sys.argv[1])
lean_repo = Path(sys.argv[2])
work_dir = Path(sys.argv[3])
result_json = Path(sys.argv[4])

loss_vector = {
    "schema_version": "p9-de/v1",
    "status": "verification_failed",
    "error_type": "postcondition_violation",
    "reconstruction_loss": {
        "violated_property": "result <= balance",
        "counter_example": {"balance": 10, "amount": 5, "result": 15},
        "loss_vector": [1.0, 5.0],
    },
    "feedback_instruction": "withdraw must subtract amount from balance",
}


class DemoAgent:
    def generate_code(self, spec: str) -> str:
        return demo_mm.read_text(encoding="utf-8")


class DemoMumeiClient:
    def verify(self, source_path: str) -> dict:
        return {"success": False, "report": {"status": "verification_failed"}}

    def verify_loss_vector(self, source_path: str) -> dict:
        return {"success": False, "loss_vector": loss_vector}


class DemoSelfCorrection:
    def __init__(self) -> None:
        self.received_loss_vector = None

    def run(self, code: str, received_loss_vector: dict) -> dict:
        self.received_loss_vector = received_loss_vector
        fixed = code.replace("body: balance + amount;", "body: balance - amount;")
        return {
            "success": True,
            "code": fixed,
            "verify_result": {
                "success": True,
                "proof_certificate": {
                    "schema_version": "p9-g/nlae-demo/v1",
                    "all_verified": True,
                    "atoms": [
                        {
                            "name": "nlae_vault_withdraw_amount_nonnegative_bound",
                            "module_key": "examples/nlae_integration_demo",
                            "z3_check_result": "unsat",
                        }
                    ],
                },
            },
            "loss_vector": received_loss_vector,
        }


class DemoLeanBridge:
    def __init__(self) -> None:
        self.invoked = False

    def run_lean_bridge(self, cert_path: Path, lean_cert_out: Path, mumei_lean_repo: Path) -> dict:
        self.invoked = True
        cert = json.loads(cert_path.read_text(encoding="utf-8"))
        lean_cert_out.write_text(json.dumps(cert, indent=2), encoding="utf-8")
        return {"success": True, "lean_cert_path": str(lean_cert_out), "lean_cert": cert}


self_correction = DemoSelfCorrection()
lean_bridge = DemoLeanBridge()
pipeline = NLAEPipeline(
    agent=DemoAgent(),
    mumei_client=DemoMumeiClient(),
    self_correction_loop=self_correction,
    lean_bridge=lean_bridge,
    work_dir=work_dir,
)
result = pipeline.run_full_pipeline("vault withdraw safety", lean_repo)
summary = {
    "scenario": "nlae_integration",
    "status": "ok" if result.verified and result.lean_verified else "failed",
    "components": {
        "module_a_av": "mumei-agent",
        "module_b_ar": "mumei",
        "fidelity_checker": "mumei-lean",
        "evaluation_loop": "mumei-demo",
    },
    "loss_vector_routed": self_correction.received_loss_vector == loss_vector,
    "self_correction_invoked": self_correction.received_loss_vector is not None,
    "lean_fallback_invoked": lean_bridge.invoked,
    "verified": result.verified,
    "lean_verified": result.lean_verified,
}
result_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2))
PY
)
