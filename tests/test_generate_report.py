from __future__ import annotations

import json
import sys
import types
import importlib.util
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from generate_report import (  # noqa: E402
    claim_book_label,
    render_scenario_markdown,
    write_summary,
)

from dashboard.cli_report import claim_book_label as cli_claim_book_label  # noqa: E402


def test_claim_book_section_is_rendered_with_counts_and_detail(tmp_path):
    data = {
        "scenario": "medical_device",
        "scenario_name": "Medical Device",
        "overall_status": "PASS",
        "proof_density": {"verified": 1, "total": 1, "percentage": 100},
        "layers": {},
        "claim_book": {
            "entries": [
                {
                    "step": "verify_correct",
                    "status": "ok",
                    "total": 3,
                    "by_effective_grade": {"G0": 0, "G1": 0, "G4": 2, "G5": 1},
                    "by_freshness": {"fresh": 3, "drifted": 0, "uncertified": 0},
                    "incomplete": 1,
                    "lowest_effective_grade": "G4",
                },
                {
                    "step": "verify_other",
                    "status": "unavailable",
                    "detail": "claims command is unavailable",
                },
            ],
            "totals": {},
        },
    }

    report = render_scenario_markdown(data, tmp_path)

    assert "## Claim Book" in report
    assert "| verify_correct | ok | 3 | 3 | 0 | 0 | 3 | 0 | 0 | 1 | G4 |" in report
    assert "unavailable: claims command is unavailable" in report
    assert "Informational: the Claim Book does not change the scenario status." in report


def test_old_result_does_not_render_claim_book_section(tmp_path):
    report = render_scenario_markdown(
        {
            "scenario": "legacy",
            "overall_status": "PASS",
            "proof_density": {},
            "layers": {},
        },
        tmp_path,
    )

    assert "## Claim Book" not in report


def test_claim_book_summary_labels():
    assert claim_book_label({}) == "N/A"
    assert claim_book_label({
        "claim_book": {"entries": [{"status": "unavailable"}], "totals": {}},
    }) == "unavailable"
    assert claim_book_label({
        "claim_book": {"entries": [{"status": "skipped"}], "totals": {}},
    }) == "skipped"
    assert claim_book_label({
        "claim_book": {
            "entries": [{"status": "ok"}],
            "totals": {
                "total": 4,
                "by_effective_grade": {"G4": 2, "G5": 1},
                "by_freshness": {"drifted": 1, "uncertified": 2},
            },
        },
    }) == "3/4 machine-sealed · 1 drifted · 2 uncertified"


def test_dashboard_claim_book_labels_match(tmp_path, monkeypatch):
    streamlit = types.ModuleType("streamlit")
    monkeypatch.setitem(sys.modules, "streamlit", streamlit)
    app_path = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"
    spec = importlib.util.spec_from_file_location("claim_book_dashboard_app", app_path)
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    data = {
        "claim_book": {
            "entries": [{"status": "ok"}],
            "totals": {
                "total": 3,
                "by_effective_grade": {"G4": 2, "G5": 1},
                "by_freshness": {"drifted": 1, "uncertified": 0},
            },
        },
    }
    expected = "3/3 machine-sealed · 1 drifted · 0 uncertified"

    assert cli_claim_book_label(data) == expected
    assert app.claim_book_label(data) == expected


def test_write_summary_includes_claim_book_label(tmp_path):
    reports = tmp_path / "reports"
    result_dir = reports / "medical_device" / "20260101T000000Z"
    result_dir.mkdir(parents=True)
    (result_dir / "result.json").write_text(
        json.dumps({
            "scenario": "medical_device",
            "overall_status": "PASS",
            "proof_density": {"verified": 3, "total": 3, "percentage": 100},
            "layers": {},
            "claim_book": {
                "entries": [{"status": "ok"}],
                "totals": {
                    "total": 3,
                    "by_effective_grade": {"G4": 3},
                    "by_freshness": {"drifted": 0, "uncertified": 0},
                },
            },
        }),
        encoding="utf-8",
    )
    output = tmp_path / "summary.md"

    assert write_summary(reports, output, ["medical_device"], False) == 0

    summary = output.read_text(encoding="utf-8")
    assert "| Claim Book |" in summary
    assert "3/3 machine-sealed · 0 drifted · 0 uncertified" in summary
