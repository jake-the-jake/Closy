from __future__ import annotations

from pathlib import Path

from closy_forge.package_io.canonical_json import read_json
from closy_forge.simulation_topology_v2.evidence import (
    INTEGRATED_D_LEDGER_PATH,
    attach_performance_measurement,
    build_final_d0_research_matrix,
    build_v2_invalidation_ledger,
)


def _minimal_report() -> dict[str, object]:
    return {
        "sourceAnchorSha": "a" * 40,
        "identities": {"simulationTopologyHash": "v2"},
        "authority": {"outcome": "A_physical_experiment_only_v2"},
        "performance": {"runtimeCeilingSeconds": 180},
        "acceptance": {
            "status": "failed",
            "checks": {"physical": False, "performance": False},
            "failedChecks": ["physical", "performance"],
            "globalPhy1Complete": False,
        },
        "claims": {"productionPhysicalAnimation": False},
        "integrity": {"evidenceHash": ""},
    }


def test_performance_measurement_never_promotes_failed_physics() -> None:
    report = attach_performance_measurement(
        _minimal_report(),  # type: ignore[arg-type]
        measured_wall_seconds=63.0,
        peak_memory_bytes=None,
        environment={"cpu": "test"},
    )

    assert report["acceptance"]["checks"]["performance"] is True
    assert report["acceptance"]["status"] == "failed"
    assert report["acceptance"]["failedChecks"] == ["physical"]


def test_outcome_a_ledger_preserves_every_integrated_runtime_identity() -> None:
    root = Path(".")
    report = _minimal_report()
    ledger = build_v2_invalidation_ledger(root, report)  # type: ignore[arg-type]
    integrated = read_json(root / INTEGRATED_D_LEDGER_PATH)

    assert ledger["baselineRuntimeIdentities"] == integrated["baselineIdentities"]
    assert ledger["currentRuntimeIdentities"] == integrated["currentIdentities"]
    assert ledger["runtimeIdentityChanges"] == []
    assert ledger["invalidatedRuntimeCapabilities"] == []
    assert ledger["separationProof"]["v2RuntimeCapabilityPublished"] is False


def test_final_d0_matrix_stays_partial_at_first_missing_exact_raster_row() -> None:
    matrix = build_final_d0_research_matrix(Path("."), _minimal_report())  # type: ignore[arg-type]

    assert matrix["rowCount"] == 14
    assert matrix["researchPrototypeStatus"] == "partial"
    assert matrix["firstUnmetRequirement"]["rowId"] == "D0-RP-01"
    assert matrix["rows"][0]["status"] == "not_run"
    assert matrix["claims"]["globalResearchPrototypePassed"] is False
