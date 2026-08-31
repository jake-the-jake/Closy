from __future__ import annotations

from pathlib import Path

from closy_forge.dependency_identity import calculate_invalidation, validate_dependency_graph
from closy_forge.package_io.canonical_json import read_json
from closy_forge.research_matrix import evaluate_research_matrix
from closy_forge.security.evidence_hygiene import scan_evidence_files

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/d0_truth_runtime_authority_v3"


def _object(path: Path) -> dict[str, object]:
    value = read_json(path)
    assert isinstance(value, dict)
    return value


def test_committed_matrix_recomputes_from_opened_exact_identity_evidence() -> None:
    bindings = _object(EVIDENCE / "matrix_evidence_bindings.json")
    registry = _object(ROOT / "docs/capability-profiles/d0-research-matrix-v2.json")
    committed = _object(EVIDENCE / "final_d0_research_prototype_matrix_v2.json")
    recomputed = evaluate_research_matrix(
        ROOT,
        registry=registry,
        evidence_bindings=bindings["evidenceBindings"],  # type: ignore[arg-type]
        selected_identity=bindings["selectedIdentity"],  # type: ignore[arg-type]
        source_anchor_sha="01699163ed4470992f0e33ff9d9b6b4c65a67f7f",
    )

    assert recomputed == committed
    assert committed["statusCounts"] == {"pass": 8, "fail": 0, "not_run": 7}
    rows = {row["rowId"]: row for row in committed["rows"]}  # type: ignore[index]
    assert rows["D0-RP-15"]["status"] == "not_run"
    assert committed["researchPrototypeStatus"] == "partial"


def test_candidate_v2_uses_garment_fallback_without_payload_overclaim() -> None:
    evidence = _object(EVIDENCE / "runtime_candidate_v2.json")
    candidate = evidence["runtimeCandidate"]
    truth = evidence["truth"]
    authority = evidence["packageAuthority"]
    assert isinstance(candidate, dict) and isinstance(truth, dict) and isinstance(authority, dict)

    assert candidate["selectedSource"] == "conventional_garment_glb"
    assert candidate["sourceWithdrawalFallbackLoadedOffline"] is True
    assert candidate["descriptorRemovalFallbackViable"] is True
    assert candidate["actualZeroOnePayloadLoaded"] is False
    assert truth["descriptorSelectableAsRenderablePayload"] is False
    assert authority["conventionalGarmentFallbackSha256"] == candidate["selectedBytesSha256"]


def test_dependency_graph_is_coherent_and_tracks_all_required_identity_stages() -> None:
    graph = _object(EVIDENCE / "dependency_identity_graph.json")
    validate_dependency_graph(graph)
    stages = {node["stage"] for node in graph["nodes"]}  # type: ignore[index]
    assert stages == {
        "decoded_source_records",
        "capture_normalisation",
        "masks_parts_landmarks_corrections_cameras",
        "template_choice_and_fitted_parameters",
        "pattern_seams_openings",
        "simulation_topology",
        "render_topology",
        "binding_and_conventional_fallback",
        "texture_pbr_material_identity",
        "optional_z1_mt1_derivatives",
        "runtime_package_and_negotiated_capability",
    }
    invalidation = calculate_invalidation(graph, {"observations"})
    assert invalidation["rebuildNodeIds"][-1] == "simulation"
    assert "runtime" in invalidation["rebuildNodeIds"]


def test_unit_a_evidence_contains_no_private_or_host_source_identifiers() -> None:
    assert scan_evidence_files(sorted(EVIDENCE.glob("*.json"))) == {}
