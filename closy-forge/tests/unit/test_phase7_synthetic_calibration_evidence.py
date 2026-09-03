from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from closy_forge.blueprint.continuation_dependency_graph import (
    build_continuation_dependency_graph,
    validate_continuation_dependency_graph,
)
from closy_forge.package_io.canonical_json import read_json
from closy_forge.simulation.material_physics import build_material_preset_registry
from closy_forge.simulation.synthetic_mechanical_calibration import (
    run_synthetic_mechanical_calibration,
)

FORGE_ROOT = Path(__file__).resolve().parents[2]
DOCS = FORGE_ROOT / "docs"
EVIDENCE = DOCS / "evidence/phase7_synthetic_mechanical_calibration_v2"


def test_continuation_graph_encodes_literal_dependencies_and_no_unrun_ready_unit() -> None:
    strategy3 = read_json(DOCS / "evidence/strategy3_blob_authority_v3/outcome_report.json")
    d0_v4 = read_json(DOCS / "evidence/d0_v4_engineering/unit_ac_outcome.json")
    status = read_json(DOCS / "current_blueprint_status.json")
    calibration = run_synthetic_mechanical_calibration(build_material_preset_registry())
    graph = build_continuation_dependency_graph(
        strategy3_outcome=strategy3,
        d0_v4_outcome=d0_v4,
        synthetic_calibration_report=calibration,
        coverage_counts=status["coverage"]["counts"],
        phase_statuses=status["phases"],
    )

    validate_continuation_dependency_graph(graph)
    nodes = {node["nodeId"]: node for node in graph["nodes"]}
    assert nodes["Z"]["status"] == "ineligible"
    assert nodes["AD"]["status"] == "ineligible"
    assert nodes["AE-03-sleeveless-image-conditioned-development"]["status"] == ("ineligible")
    assert nodes["AE-04-phase7-synthetic-mechanical-calibration"]["status"] == ("implemented")
    assert graph["coverageSnapshot"]["total"] == 101
    assert graph["coverageSnapshot"]["phase7StatusAfterUnitAE"] == "partial"
    assert graph["remainingDependencyGraph"]["dependencyReadyImplementationUnits"] == []


def test_committed_unit_ae_evidence_is_fresh_and_matches_executable_report() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/generate_phase7_synthetic_calibration_v2_evidence.py",
            "--check",
        ],
        cwd=FORGE_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    persisted = read_json(EVIDENCE / "synthetic_mechanical_calibration.json")
    expected = run_synthetic_mechanical_calibration(build_material_preset_registry())
    outcome = read_json(EVIDENCE / "unit_ae_outcome.json")
    assert persisted == expected
    assert outcome["literalOutcome"] == (
        "implemented_project_authored_synthetic_mechanical_calibration_v2"
    )
    assert outcome["phase7Status"] == "partial"
    assert outcome["dependencyGraph"]["unitAD"] == "not_run_ineligible"
