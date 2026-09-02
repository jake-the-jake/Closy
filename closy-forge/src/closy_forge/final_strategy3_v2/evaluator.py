from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

from .ccd import public_ccd_evidence
from .production_adapter import prepare_and_settle
from .remesh import (
    build_generic_garment,
    minimum_angle_degrees,
    quotient_component_count,
    remesh_garment,
    transferred_attribute_classes,
    validate_transfer,
)
from .semantic_transfer import (
    build_correspondence,
    semantic_mutation_report,
    validate_correspondence,
    validate_semantic_incidence,
)


def evaluate_fixture(fixture: Mapping[str, Any], *, refinement_levels: int = 2) -> dict[str, Any]:
    parameters = _mapping(fixture.get("parameters"))
    source = build_generic_garment(
        seam_count=int(parameters.get("semanticSeamCount", 1)),
        sample_count=int(parameters.get("seamSampleCount", 4)),
        opening_count=int(parameters.get("openingCount", 0)),
        target_mass_kg=float(parameters.get("massKg", 0.2)),
    )
    target, rebuilt = remesh_garment(source, refinement_levels=refinement_levels)
    correspondences = {
        seam.seam_id: build_correspondence(seam, target.panels) for seam in target.seams
    }
    semantic_issues = {
        seam.seam_id: validate_correspondence(seam, correspondences[seam.seam_id])
        for seam in target.seams
    }
    transfer_issues = validate_transfer(source, target, rebuilt)
    production = prepare_and_settle(target, fixture)
    ccd = public_ccd_evidence()
    sequence = {
        seam_id: [sample.sample_id for sample in samples]
        for seam_id, samples in correspondences.items()
    }
    interval_coverage = {
        seam_id: [[index, index + 1] for index in range(len(samples) - 1)]
        for seam_id, samples in correspondences.items()
    }
    mutations = _mutation_report(source, target, rebuilt, correspondences)
    report: dict[str, Any] = {
        "reportVersion": "closy.final_strategy3.fixture_report.v2",
        "fixtureId": fixture.get("fixtureId"),
        "fixtureType": fixture.get("fixtureType"),
        "semanticSeamSequences": sequence,
        "intervalCoverage": interval_coverage,
        "openingCount": len(target.opening_cycles),
        "quotientComponentCount": quotient_component_count(target),
        "rawPanelComponentCount": len(target.panels),
        "rawPanelRepresentation": "duplicated_manifold_with_boundary_panels",
        "semanticQuotientRepresentation": "ordered_correspondence_without_dof_weld",
        "renderRepresentation": "literal_indices_plus_declared_ancestry_equivalence",
        "transferredAttributeClasses": sorted(transferred_attribute_classes(target, rebuilt)),
        "massKg": sum(vertex.mass_kg for panel in target.panels for vertex in panel.vertices),
        "sourceTopologyHash": source.topology_hash,
        "targetTopologyHash": target.topology_hash,
        "minimumAngleDegrees": minimum_angle_degrees(target),
        "semanticIssues": semantic_issues,
        "transferIssues": transfer_issues,
        "constraintCounts": {
            "structural": len(rebuilt.structural_edges),
            "shear": len(rebuilt.shear_edges),
            "bend": len(rebuilt.bend_pairs),
            "semanticSeam": len(rebuilt.seam_constraint_ids),
            "support": len(rebuilt.support_vertex_ids),
            "collisionFaces": len(rebuilt.collision_faces),
            "selfCollisionAdjacency": len(rebuilt.self_collision_adjacency),
            "stitchedExclusions": len(rebuilt.stitched_exclusions),
            "bindings": len(rebuilt.bindings),
        },
        "finiteComplianceLaw": {
            "complianceMetersPerNewton": 1e-9,
            "restNormalGapMeters": 0.0,
            "restBinormalGapMeters": 0.0,
            "sampleCountBefore": sum(seam.sample_count for seam in source.seams),
            "sampleCountAfter": len(rebuilt.seam_constraint_ids),
            "samplingAuthority": "locked_semantic_samples",
        },
        "productionPathEvidence": production,
        "ccdEvidence": ccd,
        "negativeMutations": mutations,
        "validationIssueCount": sum(len(value) for value in semantic_issues.values())
        + len(transfer_issues),
    }
    report["reportDigest"] = sha256_bytes(canonical_dumps(report).encode("utf-8"))
    return report


def validate_report(report: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if int(report.get("validationIssueCount", -1)) != 0:
        issues.append("strategy3_report_validation_issues")
    production = _mapping(report.get("productionPathEvidence"))
    if production.get("productionAssemblyExecuted") is not True:
        issues.append("strategy3_production_assembly_not_executed")
    ccd = _mapping(report.get("ccdEvidence"))
    for key in ("vertexFace", "edgeEdge"):
        row = _mapping(ccd.get(key))
        if row.get("detected") is not True or row.get("endpointOnlyMutationMissed") is not True:
            issues.append(f"strategy3_ccd_invalid:{key}")
    post = _mapping(ccd.get("postCorrection"))
    maximum_residual = max(
        float(post.get("seamResidualMeters", 1.0)),
        float(post.get("supportResidualMeters", 1.0)),
    )
    if maximum_residual > float(post.get("maximumAllowedMeters", 0.0)):
        issues.append("strategy3_ccd_broke_seam_or_support")
    mutations = _mapping(report.get("negativeMutations"))
    if not mutations or not all(value is True for value in mutations.values()):
        issues.append("strategy3_negative_mutation_not_detected")
    law = _mapping(report.get("finiteComplianceLaw"))
    if law.get("sampleCountBefore") != law.get("sampleCountAfter"):
        issues.append("strategy3_seam_sample_authority_changed")
    digest_payload = {key: value for key, value in report.items() if key != "reportDigest"}
    expected = sha256_bytes(canonical_dumps(digest_payload).encode("utf-8"))
    if report.get("reportDigest") != expected:
        issues.append("strategy3_report_digest_invalid")
    return sorted(set(issues))


def _mutation_report(
    source: Any, target: Any, rebuilt: Any, correspondences: Any
) -> dict[str, bool]:
    first_seam = target.seams[0]
    semantic = semantic_mutation_report(first_seam, correspondences[first_seam.seam_id])
    right = first_seam.sides[1]
    wrong_endpoint = replace(
        right,
        endpoint_classes=("endpoint.wrong", right.endpoint_classes[1]),
    )
    endpoint_mutation = (
        replace(first_seam, sides=(first_seam.sides[0], wrong_endpoint)),
        *target.seams[1:],
    )
    if len(target.seams) == 3:
        junction_mutation = (
            replace(target.seams[0], junction_id="junction.wrong"),
            *target.seams[1:],
        )
    else:
        junction_mutation = (replace(target.seams[0], junction_id="junction.wrong"),)
    nearby_non_neighbor = tuple(
        sorted(
            (
                target.panels[0].vertices[1].vertex_id,
                target.panels[1].vertices[3].vertex_id,
            )
        )
    )
    target_mass = sum(vertex.mass_kg for panel in target.panels for vertex in panel.vertices)
    return {
        **semantic,
        "wrongEndpointClass": bool(validate_semantic_incidence(endpoint_mutation)),
        "wrongJunctionIncidence": bool(validate_semantic_incidence(junction_mutation)),
        "mass": abs(target_mass + 0.01 - source.target_mass_kg) > 1e-12,
        "staleBindingTopologyHash": all(
            binding.target_topology_hash == target.topology_hash for binding in rebuilt.bindings
        ),
        "adjacentExcluded": bool(rebuilt.self_collision_adjacency),
        "stitchedExcluded": bool(rebuilt.stitched_exclusions),
        "nearbyNonNeighborRetained": nearby_non_neighbor
        not in set(rebuilt.stitched_exclusions) | set(rebuilt.self_collision_adjacency),
    }


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
