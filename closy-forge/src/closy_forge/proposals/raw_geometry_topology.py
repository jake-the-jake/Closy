from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import audit_glb, read_glb_meshset
from closy_forge.geometry.topology_diagnostics import (
    TOPOLOGY_DIAGNOSTICS_VERSION,
    meshset_topology_diagnostics,
)
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes, sha256_file

RAW_GEOMETRY_TOPOLOGY_REPORT_VERSION = "closy.raw_geometry_topology_report.v1"


def build_raw_geometry_topology_report(
    *,
    garment_id: str,
    garment_class: str,
    raw_geometry_proposal: dict[str, Any],
    asset_path: Path,
) -> dict[str, Any]:
    glb_audit = audit_glb(asset_path)
    meshset = read_glb_meshset(asset_path)
    topology = meshset_topology_diagnostics(meshset)
    raw = raw_geometry_proposal["rawProposal"]
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "topology.raw_manual_tshirt_visual_geometry_v1",
        "stageVersion": RAW_GEOMETRY_TOPOLOGY_REPORT_VERSION,
        "analyzerVersion": TOPOLOGY_DIAGNOSTICS_VERSION,
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "sourceRawProposalId": raw_geometry_proposal["proposalId"],
        "sourceRawProposalHash": raw_geometry_proposal["integrity"]["geometryProposalHash"],
        "sourceRawAssetPath": raw["assetPath"],
        "sourceRawAssetHash": raw["sourceAssetHash"],
        "sourceRawAssetByteSize": raw["byteSize"],
        "providerId": raw_geometry_proposal["provider"]["providerId"],
        "inputAudit": {
            "meshCount": glb_audit["meshCount"],
            "visibleMeshCount": glb_audit["primitiveCount"],
            "triangleEstimate": glb_audit["triangleEstimate"],
            "materialCount": glb_audit["materialCount"],
            "nodeCount": glb_audit["nodeCount"],
            "assetHash": sha256_file(asset_path),
            "byteSize": asset_path.stat().st_size,
        },
        "topology": topology,
        "cleanReadiness": {
            "status": "rejected",
            "acceptedForCleanProposal": False,
            "blockingReasons": [
                "open_surface_requires_semantic_panel_stitching",
                "simulation_binding_missing",
                "repair_not_run",
                "canonical_acceptance_gate_not_run",
            ],
            "warnings": [
                "raw_visual_reference_only",
                "topology_diagnostics_do_not_make_geometry_canonical",
            ],
        },
        "policy": {
            "allowExternalApis": False,
            "allowTrainingUse": False,
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "approvedDomain": "avatar_and_garment_only",
        },
        "integrity": {"rawGeometryTopologyReportHash": ""},
    }
    report["integrity"]["rawGeometryTopologyReportHash"] = hash_raw_geometry_topology_report(report)
    return report


def raw_geometry_topology_quality_report(report: dict[str, Any]) -> dict[str, Any]:
    topology = report["topology"]
    readiness = report["cleanReadiness"]
    return {
        "schemaVersion": 1,
        "status": "pass",
        "reportId": report["reportId"],
        "sourceRawProposalId": report["sourceRawProposalId"],
        "sourceRawAssetPath": report["sourceRawAssetPath"],
        "meshCount": topology["meshCount"],
        "componentCount": topology["componentCount"],
        "largestComponentTriangleCount": topology["largestComponentTriangleCount"],
        "boundaryEdgeCount": topology["boundaryEdgeCount"],
        "nonManifoldEdgeCount": topology["nonManifoldEdgeCount"],
        "degenerateTriangleCount": topology["degenerateTriangleCount"],
        "duplicatePositionCount": topology["duplicatePositionCount"],
        "manifoldStatus": topology["manifoldStatus"],
        "acceptedForCleanProposal": readiness["acceptedForCleanProposal"],
        "blockingReasons": readiness["blockingReasons"],
        "warnings": readiness["warnings"],
    }


def hash_raw_geometry_topology_report(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["rawGeometryTopologyReportHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
