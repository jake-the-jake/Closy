from __future__ import annotations

import copy
from typing import Any

import pytest

from closy_forge.dependency_identity import (
    DEPENDENCY_GRAPH_VERSION,
    DependencyGraphError,
    calculate_invalidation,
    validate_dependency_graph,
)

CANDIDATE = "a" * 64


def _node(node_id: str, stage: str, *, portable: bool = True) -> dict[str, Any]:
    return {
        "nodeId": node_id,
        "stage": stage,
        "identity": (
            {"opaqueLineageId": f"lineage_{node_id}"}
            if portable
            else {"restrictedRegistryHandle": f"restricted_{node_id}"}
        ),
        "authorityId": f"authority.{node_id}",
        "classification": "portable_opaque" if portable else "private_restricted",
        "portable": portable,
        "packageCandidateId": CANDIDATE,
    }


def _graph() -> dict[str, Any]:
    stages = [
        ("source", "decoded_source_records", False),
        ("capture", "capture_normalisation", True),
        ("observations", "masks_parts_landmarks_corrections_cameras", True),
        ("fit", "template_choice_and_fitted_parameters", True),
        ("pattern", "pattern_seams_openings", True),
        ("simulation", "simulation_topology", True),
        ("render", "render_topology", True),
        ("binding", "binding_and_fallback", True),
        ("appearance", "texture_pbr_material_identity", True),
        ("derivatives", "optional_z1_mt1_derivatives", True),
        ("runtime", "runtime_package_and_negotiated_capability", True),
    ]
    nodes = [_node(node_id, stage, portable=portable) for node_id, stage, portable in stages]
    edges = []
    for left, right in zip(stages, stages[1:], strict=False):
        edges.append(
            {
                "fromNodeId": left[0],
                "toNodeId": right[0],
                "onUpstreamIdentityChange": "rebuild",
                "rationale": f"{right[0]} is derived from {left[0]}",
            }
        )
    edges.append(
        {
            "fromNodeId": "source",
            "toNodeId": "runtime",
            "onUpstreamIdentityChange": "byte_identical",
            "rationale": "withdrawn private source is not required by self-contained fallback",
        }
    )
    return {
        "schemaVersion": 1,
        "graphVersion": DEPENDENCY_GRAPH_VERSION,
        "packageCandidateId": CANDIDATE,
        "nodes": nodes,
        "edges": edges,
        "identityPolicy": {
            "privateInputs": "restricted_registry_handles_only",
            "portableAuthority": "opaque_lineage_and_exported_artifact_hashes",
            "publicFixtureException": "explicit_public_fixture_only",
            "offlineFallbackRequiresRestrictedRegistry": False,
        },
    }


def test_dependency_graph_propagates_source_correction_fit_uv_and_material_changes() -> None:
    graph = _graph()
    validate_dependency_graph(graph)
    source = calculate_invalidation(graph, {"source"})
    assert "capture" in source["rebuildNodeIds"]
    assert "runtime" in source["rebuildNodeIds"]
    correction = calculate_invalidation(graph, {"observations"})
    assert correction["rebuildNodeIds"] == [
        "appearance",
        "binding",
        "derivatives",
        "fit",
        "pattern",
        "render",
        "runtime",
        "simulation",
    ]
    appearance = calculate_invalidation(graph, {"appearance"})
    assert appearance["rebuildNodeIds"] == ["derivatives", "runtime"]


@pytest.mark.parametrize("defect", ["cycle", "unknown", "duplicate_authority", "cross_candidate"])
def test_dependency_graph_rejects_invalid_authority_graphs(defect: str) -> None:
    graph = _graph()
    if defect == "cycle":
        graph["edges"].append(
            {
                "fromNodeId": "runtime",
                "toNodeId": "source",
                "onUpstreamIdentityChange": "invalidate",
                "rationale": "invalid cycle",
            }
        )
    elif defect == "unknown":
        graph["edges"][0]["toNodeId"] = "unknown"
    elif defect == "duplicate_authority":
        graph["nodes"][1]["authorityId"] = graph["nodes"][0]["authorityId"]
    else:
        graph["nodes"][1]["packageCandidateId"] = "b" * 64
    with pytest.raises(DependencyGraphError):
        validate_dependency_graph(graph)


def test_portable_graph_rejects_private_source_fingerprint() -> None:
    graph = _graph()
    portable = copy.deepcopy(graph["nodes"][1])
    portable["identity"]["rawSourceSha256"] = "c" * 64
    graph["nodes"][1] = portable
    with pytest.raises(DependencyGraphError, match="restricted_source"):
        validate_dependency_graph(graph)


def test_public_fixture_hashes_require_explicit_classification() -> None:
    graph = _graph()
    source = graph["nodes"][0]
    source["classification"] = "public_fixture"
    source["portable"] = True
    source["identity"] = {"publicFixtureSha256": "d" * 64}
    validate_dependency_graph(graph)
