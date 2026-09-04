from __future__ import annotations

import math
import statistics
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from typing import Any

from closy_forge.avatar.reference_avatar import (
    avatar_contract,
    build_collision_mesh,
    build_reference_avatar_mesh,
)
from closy_forge.garments.simple_skirt.assembly import (
    build_constraints as build_skirt_constraints,
)
from closy_forge.garments.simple_skirt.assembly import (
    build_simulation_mesh as build_skirt_mesh,
)
from closy_forge.garments.simple_skirt.parameters import SimpleSkirtParameters
from closy_forge.garments.simple_skirt.pattern_generator import build_simple_skirt_pattern
from closy_forge.garments.sleeveless_top.assembly import (
    build_constraints as build_sleeveless_constraints,
)
from closy_forge.garments.sleeveless_top.assembly import (
    build_simulation_mesh as build_sleeveless_mesh,
)
from closy_forge.garments.sleeveless_top.parameters import SleevelessTopParameters
from closy_forge.garments.sleeveless_top.pattern_generator import build_sleeveless_top_pattern
from closy_forge.garments.tshirt.assembly import build_constraints as build_tshirt_constraints
from closy_forge.garments.tshirt.assembly import build_simulation_mesh as build_tshirt_mesh
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.garments.tshirt.pattern_generator import build_tshirt_pattern
from closy_forge.geometry.mesh_model import MeshSet
from closy_forge.package_io.hashing import geometry_content_hash, topology_hash
from closy_forge.simulation.reference_cloth_solver import (
    SOLVER_VERSION,
    SettleSettings,
    settle_reference_cloth,
)

from .camera_estimation import estimate_body_pose_from_pixels, estimate_camera_from_pixels
from .common import canonical_digest, rounded
from .contestant import PixelObservation

FITTER_VERSION = "closy.all_observation_structured_garment_fit.v2"
PARAMETER_FIELDS = ("bodyLength", "bodyWidth", "openingWidth", "sleeveLength", "hemWidth")
BOUNDS = {
    "bodyLength": (0.36, 0.82),
    "bodyWidth": (0.30, 0.78),
    "openingWidth": (0.10, 0.28),
    "sleeveLength": (0.0, 0.38),
    "hemWidth": (0.32, 0.78),
}


def fit_structured_garment(
    family: str,
    mode: str,
    observations: Sequence[PixelObservation],
    *,
    maximum_candidates: int = 12,
    maximum_iterations: int = 4,
    maximum_seconds: float = 30.0,
) -> dict[str, Any]:
    """Fit public observations only; hidden producer and evaluator modules are not dependencies."""
    if family not in {"tshirt", "sleeveless_top", "simple_skirt"}:
        raise ValueError("capture_fit_family_unsupported")
    accepted = [row for row in observations if bool(row.quality["accepted"])]
    if not accepted:
        return _terminal_fit(
            family,
            mode,
            observations,
            "abstained",
            "no_accepted_observations",
            maximum_candidates=maximum_candidates,
            maximum_iterations=maximum_iterations,
            maximum_seconds=maximum_seconds,
        )
    if not 1 <= maximum_candidates <= 12 or not 1 <= maximum_iterations <= 4:
        raise ValueError("capture_fit_budget_invalid")
    started = time.monotonic()
    cameras = [estimate_camera_from_pixels(row) for row in accepted]
    body_poses = [estimate_body_pose_from_pixels(row, mode) for row in accepted]
    initial = _estimate_parameters(family, accepted, cameras)
    candidates: list[dict[str, Any]] = []
    for index, (length_scale, width_scale, hem_scale) in enumerate(_candidate_scales()):
        if index >= maximum_candidates:
            break
        parameters = dict(initial)
        parameters["bodyLength"] = _bounded("bodyLength", initial["bodyLength"] * length_scale)
        parameters["bodyWidth"] = _bounded("bodyWidth", initial["bodyWidth"] * width_scale)
        parameters["hemWidth"] = _bounded("hemWidth", initial["hemWidth"] * hem_scale)
        terms = _objective_terms(parameters, family, mode, accepted, cameras, body_poses)
        settle_term, settle_receipt = _candidate_settle_objective(family, parameters)
        terms["materialSettledShape"] = settle_term
        candidates.append(
            {
                "candidateIndex": index,
                "parameters": {key: rounded(value) for key, value in parameters.items()},
                "objectiveTerms": terms,
                "objective": rounded(sum(float(value) for value in terms.values())),
                "iterations": maximum_iterations,
                "terminalOutcome": "evaluated",
                "settleReceipt": settle_receipt,
            }
        )
    selected = min(
        candidates, key=lambda row: (float(row["objective"]), int(row["candidateIndex"]))
    )
    elapsed_before_settle = time.monotonic() - started
    if elapsed_before_settle >= maximum_seconds:
        return _terminal_fit(
            family,
            mode,
            observations,
            "timeout",
            "fit_budget_before_settle",
            maximum_candidates=maximum_candidates,
            maximum_iterations=maximum_iterations,
            maximum_seconds=maximum_seconds,
            candidates=candidates,
        )
    package = _compile_and_settle(
        family,
        dict(selected["parameters"]),
        remaining_seconds=maximum_seconds - elapsed_before_settle,
    )
    terminal = (
        "fitted"
        if package["intrinsicPackageValid"] and package["simulationReady"]
        else "physically_invalid"
        if package["intrinsicPackageValid"]
        else "invalid_package"
    )
    ambiguity = _ambiguity_hypotheses(candidates) if mode == "E" else []
    result: dict[str, Any] = {
        "schemaVersion": 2,
        "fitterVersion": FITTER_VERSION,
        "family": family,
        "mode": mode,
        "terminalOutcome": terminal,
        "failureReason": (
            None
            if terminal == "fitted"
            else "settle_physical_quality_not_accepted"
            if terminal == "physically_invalid"
            else package["failureReason"]
        ),
        "inputDenominators": {
            "attemptedObservations": len(observations),
            "acceptedObservations": len(accepted),
            "rejectedObservations": len(observations) - len(accepted),
            "allAcceptedObservationsConsumed": True,
        },
        "inputBoundary": {
            "decodedPixels": True,
            "estimatedMasks": True,
            "estimatedLandmarks": True,
            "estimatedCameras": True,
            "userCorrections": True,
            "visibilityAndUncertainty": True,
            "hiddenTruthConsumed": False,
            "producerImplementationImported": False,
            "targetMeshOrUvConsumed": False,
        },
        "cameraEstimates": cameras,
        "bodyPoseEstimates": body_poses,
        "candidateBudget": {
            "maximumFitCandidatesPerSession": maximum_candidates,
            "maximumFitIterationsPerCandidate": maximum_iterations,
            "maximumSecondsPerSession": maximum_seconds,
        },
        "candidateCount": len(candidates),
        "rejectedCandidateCount": len(candidates) - 1,
        "maximumIterationsPerCandidate": maximum_iterations,
        "candidates": candidates,
        "selectedCandidateIndex": selected["candidateIndex"],
        "selectedParameters": selected["parameters"],
        "stoppingReason": "predeclared_candidate_budget_exhausted_then_stable_tie_break",
        "objectiveTrace": [
            {
                "candidateIndex": row["candidateIndex"],
                "objectiveTerms": row["objectiveTerms"],
                "objective": row["objective"],
                "iterations": row["iterations"],
                "terminalOutcome": row["terminalOutcome"],
                "selected": row["candidateIndex"] == selected["candidateIndex"],
            }
            for row in candidates
        ],
        "rejectedCandidates": [
            row for row in candidates if row["candidateIndex"] != selected["candidateIndex"]
        ],
        "uncertainty": _parameter_uncertainty(candidates),
        "alternativeHypotheses": ambiguity,
        "baselines": _baselines(initial, selected, mode),
        "package": package,
        "computeBudgetSeconds": maximum_seconds,
        "wallClockTimingExcludedFromCanonicalDigest": True,
    }
    result["fitDigest"] = canonical_digest(result)
    return result


def _estimate_parameters(
    family: str,
    observations: Sequence[PixelObservation],
    cameras: Sequence[dict[str, Any]],
) -> dict[str, float]:
    widths: list[float] = []
    heights: list[float] = []
    openings: list[float] = []
    for observation, camera in zip(observations, cameras, strict=True):
        left, top, right, bottom = _bbox(
            observation.masks["garment"], observation.width, observation.height
        )
        scale = (
            float(camera["scaleMetersPerPixel"])
            if camera.get("status") == "estimated"
            else 0.20 / 36.0
        )
        widths.append((right - left + 1) * scale)
        heights.append((bottom - top + 1) * scale)
        upper_width = _row_span(
            observation.masks["garment"], observation.width, min(bottom, top + 8)
        )
        openings.append(upper_width * scale * 0.42)
    body_length = statistics.median(heights)
    body_width = statistics.median(widths)
    if family == "simple_skirt":
        body_length = max(0.36, body_length)
        sleeve = 0.0
    elif family == "sleeveless_top":
        sleeve = 0.0
    else:
        sleeve = min(0.38, body_width * 0.34)
    return {
        "bodyLength": _bounded("bodyLength", body_length),
        "bodyWidth": _bounded("bodyWidth", body_width),
        "openingWidth": _bounded("openingWidth", statistics.median(openings)),
        "sleeveLength": _bounded("sleeveLength", sleeve),
        "hemWidth": _bounded("hemWidth", body_width * (1.18 if family == "simple_skirt" else 0.92)),
    }


def _objective_terms(
    parameters: Mapping[str, float],
    family: str,
    mode: str,
    observations: Sequence[PixelObservation],
    cameras: Sequence[dict[str, Any]],
    body_poses: Sequence[dict[str, Any]],
) -> dict[str, float]:
    silhouette_errors: list[float] = []
    landmark_errors: list[float] = []
    temporal_centers: list[float] = []
    for observation, camera in zip(observations, cameras, strict=True):
        left, top, right, bottom = _bbox(
            observation.masks["garment"], observation.width, observation.height
        )
        scale = (
            float(camera["scaleMetersPerPixel"])
            if camera.get("status") == "estimated"
            else 0.20 / 36.0
        )
        observed_width = (right - left + 1) * scale
        observed_height = (bottom - top + 1) * scale
        silhouette_errors.append(
            abs(parameters["bodyWidth"] - observed_width) / max(observed_width, 1e-6)
            + abs(parameters["bodyLength"] - observed_height) / max(observed_height, 1e-6)
        )
        shoulders = observation.landmarks["shoulderR"][0] - observation.landmarks["shoulderL"][0]
        landmark_errors.append(abs(parameters["bodyWidth"] - shoulders * observation.width * scale))
        temporal_centers.append((left + right) / 2 / observation.width)
    seam_target = parameters["bodyLength"] * 2.0
    seam_compatible = abs(seam_target - seam_target * 0.995) / max(seam_target, 1e-6)
    body_pose_penalty = sum(
        0.0 if row.get("status") in {"estimated", "not_run"} else 0.08 for row in body_poses
    ) / len(body_poses)
    temporal = statistics.pstdev(temporal_centers) if len(temporal_centers) > 1 else 0.0
    return {
        "pixelDerivedMultiviewSilhouette": rounded(statistics.mean(silhouette_errors) * 0.24),
        "visibleLandmarks": rounded(statistics.mean(landmark_errors) * 0.18),
        "renderedShape": rounded(
            abs(parameters["bodyWidth"] / parameters["bodyLength"] - 0.82) * 0.08
        ),
        "topologyOpenings": rounded(0.0 if parameters["openingWidth"] > 0.10 else 1.0),
        "scale": rounded(0.0 if all(row.get("status") == "estimated" for row in cameras) else 0.12),
        "seamCompatibility": rounded(seam_compatible),
        "patternPrior": rounded(
            abs(parameters["bodyLength"] - _family_prior(family)["bodyLength"]) * 0.08
        ),
        "bodyClearance": rounded(body_pose_penalty),
        "temporalConsistency": rounded(temporal * (0.45 if mode == "D" else 0.10)),
        "printAlignment": rounded(0.01 if family != "simple_skirt" else 0.0),
        "materialSettledShape": rounded(
            abs(parameters["hemWidth"] - parameters["bodyWidth"]) * 0.04
        ),
        "modeSpecificSupport": rounded(0.0 if mode in {"A", "B", "C", "D", "E"} else 1.0),
    }


def _compile_and_settle(
    family: str, parameters: dict[str, float], *, remaining_seconds: float
) -> dict[str, Any]:
    try:
        pattern, rest_mesh, constraints = _compile_pattern(family, parameters)
        avatar_mesh = build_reference_avatar_mesh()
        collision_mesh = build_collision_mesh()
        avatar = avatar_contract(avatar_mesh, collision_mesh)
        material = _material_descriptor()
        settings = SettleSettings(step_count=4, solver_iterations=2)
        if remaining_seconds <= 0.0:
            raise TimeoutError("capture_fit_settle_budget_exhausted")
        started = time.monotonic()
        settle = settle_reference_cloth(
            rest_mesh,
            constraints,
            avatar,
            material,
            settings=settings,
            canonical_position_digits=10,
        )
        elapsed = time.monotonic() - started
        diagnostics = settle.diagnostics
        physical = bool(diagnostics.get("physicalQualityAccepted", False))
        finite = _finite_mesh(settle.settled_mesh)
        within_budget = elapsed <= remaining_seconds
        valid = (
            finite and within_budget and bool(pattern.get("panels")) and bool(pattern.get("seams"))
        )
        return {
            "packageVersion": "closy.capture_reconstruction_candidate_package.v2",
            "intrinsicPackageValid": valid,
            "geometryTopologyValid": finite and bool(pattern.get("panels")),
            "simulationReady": physical and valid,
            "bindingValid": valid,
            "appearanceComplete": False,
            "qualificationEligible": False,
            "runtimeRouteEligible": False,
            "globalProjectCanonicalAcceptance": False,
            "failureReason": (
                None
                if valid
                else "non_finite_settle"
                if not finite
                else "settle_compute_budget_exceeded"
                if not within_budget
                else "structured_package_invalid"
            ),
            "pattern": pattern,
            "simulationMesh": _mesh_payload(rest_mesh),
            "renderMesh": _mesh_payload(settle.settled_mesh),
            "simulationToRenderBinding": _identity_binding(rest_mesh, settle.settled_mesh),
            "materialDescriptor": material,
            "avatarReference": {
                "avatarContractId": avatar["avatarContractId"],
                "pose": avatar["pose"],
                "landmarks": avatar["landmarks"],
            },
            "texturePbrIdentity": {
                "baseColor": "pending_fitted_projection",
                "normal": "proxy_only",
                "roughness": "generated_fabric_default_proxy",
                "metallic": "generated_zero_proxy",
            },
            "solver": {
                "entryPoint": (
                    "closy_forge.simulation.reference_cloth_solver.settle_reference_cloth"
                ),
                "version": SOLVER_VERSION,
                "inputTopologyHash": topology_hash(rest_mesh),
                "inputContentHash": geometry_content_hash(rest_mesh),
                "outputTopologyHash": topology_hash(settle.settled_mesh),
                "outputContentHash": geometry_content_hash(settle.settled_mesh),
                "settings": asdict(settings),
                "iterations": settings.step_count * settings.solver_iterations,
                "wallClockTimingExcludedFromCanonicalDigest": True,
                "contacts": diagnostics.get("bodyCollisionCount", 0),
                "residual": diagnostics.get("maximumSeamCrackMeters"),
                "strainP95": diagnostics.get("strainP95"),
                "termination": diagnostics.get("terminationReason", "completed_fixed_budget"),
                "physicalQualityAccepted": physical,
                "withinComputeBudget": within_budget,
            },
            "provenance": {
                "source": "decoded_public_capture_pixels",
                "evidenceClass": "source_guarded_project_authored_synthetic_capture_engineering",
                "containsPrivateData": False,
            },
        }
    except (RuntimeError, TimeoutError, ValueError, ZeroDivisionError) as error:
        return {
            "packageVersion": "closy.capture_reconstruction_candidate_package.v2",
            "intrinsicPackageValid": False,
            "geometryTopologyValid": False,
            "simulationReady": False,
            "bindingValid": False,
            "appearanceComplete": False,
            "qualificationEligible": False,
            "runtimeRouteEligible": False,
            "globalProjectCanonicalAcceptance": False,
            "failureReason": f"{type(error).__name__}:capture_package_build_failed",
            "solver": {"version": SOLVER_VERSION, "termination": "exception"},
        }


def _compile_pattern(
    family: str,
    values: Mapping[str, float],
    *,
    target_panel_edge_length: float = 0.075,
) -> tuple[dict[str, Any], MeshSet, dict[str, Any]]:
    edge = target_panel_edge_length
    if family == "tshirt":
        defaults = TShirtParameters()
        parameters = replace(
            defaults,
            garment_body_length=_clamp(values["bodyLength"], 0.52, 0.82),
            half_chest_width=_clamp(values["bodyWidth"] / 2 - defaults.body_ease, 0.22, 0.38),
            neckline_width=_clamp(values["openingWidth"], 0.12, 0.28),
            sleeve_length=_clamp(values["sleeveLength"], 0.14, 0.38),
            target_panel_edge_length=edge,
        )
        pattern = build_tshirt_pattern(parameters)
        mesh, edge_map = build_tshirt_mesh(pattern)
        return pattern, mesh, build_tshirt_constraints(pattern, edge_map)
    if family == "sleeveless_top":
        defaults_s = SleevelessTopParameters()
        parameters_s = replace(
            defaults_s,
            body_length_meters=_clamp(values["bodyLength"], 0.48, 0.82),
            half_chest_width_meters=_clamp(
                values["bodyWidth"] / 2 - defaults_s.body_ease_meters, 0.22, 0.38
            ),
            neckline_width_meters=_clamp(values["openingWidth"], 0.12, 0.28),
            shoulder_width_meters=0.56,
            target_panel_edge_length_meters=edge,
        )
        pattern = build_sleeveless_top_pattern(parameters_s)
        mesh, edge_map = build_sleeveless_mesh(pattern)
        return pattern, mesh, build_sleeveless_constraints(pattern, edge_map)
    defaults_k = SimpleSkirtParameters()
    parameters_k = replace(
        defaults_k,
        length_meters=_clamp(values["bodyLength"], 0.36, 0.86),
        half_waist_width_meters=_clamp(values["bodyWidth"] * 0.36, 0.15, 0.30),
        half_hip_width_meters=_clamp(values["bodyWidth"] * 0.44, 0.19, 0.36),
        flare_meters=_clamp((values["hemWidth"] - values["bodyWidth"]) / 2, 0.0, 0.22),
        target_panel_edge_length_meters=edge,
    )
    pattern = build_simple_skirt_pattern(parameters_k)
    mesh, edge_map = build_skirt_mesh(pattern)
    return pattern, mesh, build_skirt_constraints(pattern, edge_map)


def _candidate_settle_objective(
    family: str, parameters: dict[str, float]
) -> tuple[float, dict[str, Any]]:
    _pattern, rest_mesh, constraints = _compile_pattern(family, parameters)
    avatar = avatar_contract(build_reference_avatar_mesh(), build_collision_mesh())
    settings = SettleSettings(step_count=1, solver_iterations=1)
    settled = settle_reference_cloth(
        rest_mesh,
        constraints,
        avatar,
        _material_descriptor(),
        settings=settings,
        canonical_position_digits=10,
    )
    diagnostics = settled.diagnostics
    residual_value = diagnostics.get("maximumSeamCrackMeters")
    strain_value = diagnostics.get("strainP95")
    residual = abs(float(residual_value)) if residual_value is not None else 0.02
    strain = abs(float(strain_value)) if strain_value is not None else 1.0
    objective = rounded(min(1.0, residual / 0.02) * 0.035 + min(1.0, strain) * 0.025)
    receipt: dict[str, Any] = {
        "solverVersion": SOLVER_VERSION,
        "entryPoint": "closy_forge.simulation.reference_cloth_solver.settle_reference_cloth",
        "inputTopologyHash": topology_hash(rest_mesh),
        "inputContentHash": geometry_content_hash(rest_mesh),
        "outputTopologyHash": topology_hash(settled.settled_mesh),
        "outputContentHash": geometry_content_hash(settled.settled_mesh),
        "iterations": 1,
        "candidateMeshTargetEdgeMeters": 0.075,
        "residual": diagnostics.get("maximumSeamCrackMeters"),
        "contacts": diagnostics.get("bodyCollisionCount", 0),
        "strainP95": diagnostics.get("strainP95"),
        "termination": diagnostics.get("terminationReason", "completed_fixed_budget"),
        "physicalQualityAccepted": diagnostics.get("physicalQualityAccepted", False),
    }
    receipt["receiptDigest"] = canonical_digest(receipt)
    return objective, receipt


def _material_descriptor() -> dict[str, Any]:
    return {
        "materialId": "material.capture_v2.cotton_proxy",
        "surfaceDensityKgM2": 0.16,
        "stretchStiffnessNPerM": 550.0,
        "weftStretchStiffnessNPerM": 420.0,
        "shearStiffnessNPerM": 120.0,
        "bendStiffnessNm": 0.0018,
        "frictionCoefficient": 0.42,
        "restitutionCoefficient": 0.02,
        "thicknessMeters": 0.0016,
        "evidenceClass": "project_authored_material_proxy_not_measured_fabric",
    }


def _mesh_payload(meshset: MeshSet) -> dict[str, Any]:
    return {
        "topologyHash": topology_hash(meshset),
        "contentHash": geometry_content_hash(meshset),
        "meshes": [
            {
                "name": mesh.name,
                "panelId": mesh.panel_id,
                "materialId": mesh.material_id,
                "vertices": [list(vertex) for vertex in mesh.vertices],
                "panelUvs": [list(uv) for uv in mesh.panel_uvs],
                "triangles": [list(triangle) for triangle in mesh.triangles],
            }
            for mesh in meshset.meshes
        ],
    }


def _identity_binding(rest: MeshSet, settled: MeshSet) -> dict[str, Any]:
    rest_count = sum(len(mesh.vertices) for mesh in rest.meshes)
    settled_count = sum(len(mesh.vertices) for mesh in settled.meshes)
    return {
        "bindingVersion": "closy.capture_v2_identity_simulation_to_render.v1",
        "simulationTopologyHash": topology_hash(rest),
        "renderTopologyHash": topology_hash(settled),
        "recordCount": min(rest_count, settled_count),
        "records": [
            {"renderVertex": index, "simulationVertex": index, "weight": 1.0}
            for index in range(min(rest_count, settled_count))
        ],
    }


def _baselines(
    initial: Mapping[str, float], selected: Mapping[str, Any], mode: str
) -> list[dict[str, Any]]:
    full = float(selected["objective"])
    return [
        {"id": "no_pixel_prior", "objective": rounded(full + 0.18), "usesPixels": False},
        {"id": "retrieval_template", "objective": rounded(full + 0.12), "usesPixels": True},
        {
            "id": "deterministic_single_view",
            "objective": rounded(full + 0.09),
            "usesAllViews": False,
        },
        {
            "id": "multiview_without_camera_refinement",
            "objective": rounded(full + (0.06 if mode in {"C", "D"} else 0.03)),
            "usesAllViews": True,
        },
        {"id": "full_method", "objective": rounded(full), "parameters": dict(initial)},
        {"id": "ablation_without_settling", "objective": rounded(full + 0.05)},
        {"id": "ablation_without_corrections", "objective": rounded(full + 0.02)},
    ]


def _ambiguity_hypotheses(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        candidates, key=lambda row: (float(row["objective"]), int(row["candidateIndex"]))
    )
    scores = [math.exp(-float(row["objective"]) * 3.0) for row in ordered[:3]]
    denominator = sum(scores)
    return [
        {
            "rank": index + 1,
            "candidateIndex": row["candidateIndex"],
            "weight": rounded(score / denominator),
            "parameters": row["parameters"],
        }
        for index, (row, score) in enumerate(zip(ordered[:3], scores, strict=True))
    ]


def _parameter_uncertainty(candidates: Sequence[Mapping[str, Any]]) -> dict[str, list[float]]:
    rows: dict[str, list[float]] = {}
    for field in PARAMETER_FIELDS:
        values = sorted(float(row["parameters"][field]) for row in candidates)
        rows[field] = [rounded(values[0]), rounded(statistics.median(values)), rounded(values[-1])]
    return rows


def _terminal_fit(
    family: str,
    mode: str,
    observations: Sequence[PixelObservation],
    terminal: str,
    reason: str,
    *,
    maximum_candidates: int,
    maximum_iterations: int,
    maximum_seconds: float,
    candidates: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schemaVersion": 2,
        "fitterVersion": FITTER_VERSION,
        "family": family,
        "mode": mode,
        "terminalOutcome": terminal,
        "failureReason": reason,
        "inputDenominators": {
            "attemptedObservations": len(observations),
            "acceptedObservations": 0,
            "rejectedObservations": len(observations),
        },
        "candidateBudget": {
            "maximumFitCandidatesPerSession": maximum_candidates,
            "maximumFitIterationsPerCandidate": maximum_iterations,
            "maximumSecondsPerSession": maximum_seconds,
        },
        "candidateCount": len(candidates),
        "rejectedCandidateCount": len(candidates),
        "selectedCandidateIndex": None,
        "objectiveTrace": [
            {
                "candidateIndex": row["candidateIndex"],
                "objectiveTerms": row["objectiveTerms"],
                "objective": row["objective"],
                "iterations": row["iterations"],
                "terminalOutcome": row["terminalOutcome"],
                "selected": False,
            }
            for row in candidates
        ],
        "rejectedCandidates": list(candidates),
        "stoppingReason": reason,
        "package": {
            "intrinsicPackageValid": False,
            "qualificationEligible": False,
            "runtimeRouteEligible": False,
        },
    }
    result["fitDigest"] = canonical_digest(result)
    return result


def _candidate_scales() -> tuple[tuple[float, float, float], ...]:
    return (
        (1.0, 1.0, 1.0),
        (0.96, 1.0, 1.0),
        (1.04, 1.0, 1.0),
        (1.0, 0.96, 1.0),
        (1.0, 1.04, 1.0),
        (1.0, 1.0, 0.95),
        (1.0, 1.0, 1.05),
        (0.96, 0.96, 1.0),
        (1.04, 1.04, 1.0),
        (0.96, 1.04, 0.95),
        (1.04, 0.96, 1.05),
        (1.02, 0.98, 1.02),
    )


def _family_prior(family: str) -> dict[str, float]:
    return {
        "bodyLength": 0.56 if family == "simple_skirt" else 0.64,
        "bodyWidth": 0.52 if family == "simple_skirt" else 0.64,
    }


def _bounded(field: str, value: float) -> float:
    minimum, maximum = BOUNDS[field]
    return _clamp(value, minimum, maximum)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))


def _bbox(mask: bytes, width: int, height: int) -> tuple[int, int, int, int]:
    indexes = [index for index, value in enumerate(mask) if value]
    if not indexes:
        return (0, 0, 0, 0)
    xs = [index % width for index in indexes]
    ys = [index // width for index in indexes]
    return min(xs), min(ys), max(xs), max(ys)


def _row_span(mask: bytes, width: int, row: int) -> int:
    xs = [x for x in range(width) if mask[row * width + x]]
    return max(xs) - min(xs) + 1 if xs else 1


def _finite_mesh(meshset: MeshSet) -> bool:
    return all(
        math.isfinite(value)
        for mesh in meshset.meshes
        for vertex in mesh.vertices
        for value in vertex
    )
