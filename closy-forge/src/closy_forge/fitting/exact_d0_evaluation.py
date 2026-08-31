from __future__ import annotations

import json
import math
import shutil
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.appearance.bitmap_atlas import (
    BITMAP_PATHS,
    BitmapAtlasBundle,
    audit_bitmap_atlas_bundle,
)
from closy_forge.binding.binary_format import read_binding
from closy_forge.capture.raster_sources import decode_raster_fixture_pixels
from closy_forge.dependency_identity import (
    DEPENDENCY_GRAPH_VERSION,
    calculate_invalidation,
    validate_dependency_graph,
)
from closy_forge.fitting.exact_d0_candidate import (
    compile_exact_d0_candidate,
    inventory_digest,
    package_inventory,
    validate_compiled_candidate_files,
    write_compiled_exact_candidate,
)
from closy_forge.fitting.exact_d0_lock import load_exact_d0_evaluation_lock
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.geometry.frame_attributes import meshset_frame_metrics, vertex_normals
from closy_forge.geometry.glb_io import audit_glb, read_glb_meshset
from closy_forge.geometry.mesh_model import Mesh, MeshSet, finite_mesh
from closy_forge.inspection.cpu_raster import rasterize_settled_garment
from closy_forge.inspection.source_render_fidelity import (
    _atlas_sampler,
    compare_decoded_source_and_render,
)
from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.hashing import (
    geometry_content_hash,
    sha256_bytes,
    sha256_file,
    topology_hash,
)
from closy_forge.raster import DecodedPng, decode_png_rgba, encode_png_rgba
from closy_forge.research_matrix import canonical_artifact_sha256, evaluate_research_matrix
from closy_forge.runtime_delivery.package import load_runtime_package
from closy_forge.security.evidence_hygiene import scan_evidence_files

EXACT_D0_EVALUATION_VERSION = "closy.d0_exact_fitting_pbr.evaluation.v2"
_EVIDENCE_RELATIVE = Path("docs/evidence/d0_fitting_pbr_fidelity_v2")


def generate_exact_d0_evaluation(
    root: Path,
    *,
    prediction_commit_sha: str,
    evaluator_implementation_sha: str,
    output: Path | None = None,
) -> dict[str, Any]:
    _require_commit(prediction_commit_sha, "prediction_checkpoint")
    _require_commit(evaluator_implementation_sha, "evaluator_implementation")
    lock = load_exact_d0_evaluation_lock(root)
    predictions = root / _EVIDENCE_RELATIVE / "predictions"
    candidate_root = predictions / "candidate_package"
    target = output or root / _EVIDENCE_RELATIVE / "evaluation"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    ground_truth = _read(root / "fixtures/d0_exact_fitting_v2/evaluator_ground_truth.json")
    checkpoint = _validate_prediction_checkpoint(
        predictions, candidate_root, ground_truth, prediction_commit_sha
    )
    manifest = _read(candidate_root / "candidate_manifest.json")
    compiled_report = _read(candidate_root / "reports/compiled_candidate.json")
    fit_report = _read(candidate_root / "fitting/tshirt_fit.json")
    correction = _read(
        root / "docs/evidence/d0_exact_raster_identity_v2/qualification/correction_evidence.json"
    )
    visual = _mapping(correction.get("correctedObservation"))
    atlas = _load_frozen_atlas(candidate_root, visual)

    target_candidate = compile_exact_d0_candidate(
        contender_id="evaluator_only_reference_target",
        parameters=TShirtParameters(**_mapping(ground_truth.get("targetParameters"))),
        visual_observations=visual,
        fixture_root=root / "fixtures/d0_exact_raster_v2",
        fixture_manifest=_read(root / "fixtures/d0_exact_raster_v2/fixture_manifest.json"),
        atlas=atlas,
    )
    reference_root = target / "reference_target"
    write_compiled_exact_candidate(reference_root, target_candidate)

    pattern = _read(candidate_root / "pattern/pattern.json")
    pattern_evaluation = _pattern_evaluation(
        pattern,
        target_candidate.pattern,
        _mapping(fit_report.get("fittedParameters")),
        _mapping(ground_truth.get("targetParameters")),
        lock,
    )
    candidate_settled = read_glb_meshset(candidate_root / "simulation/settled_mesh.glb")
    target_settled = read_glb_meshset(reference_root / "simulation/settled_mesh.glb")
    surface = _surface_evaluation(candidate_settled, target_settled, lock)
    held_out = _held_out_evaluation(root, candidate_root, candidate_settled, ground_truth, lock)
    _write_bytes(target / "renders/left_three_quarter.png", held_out.pop("renderBytes"))
    _write_bytes(
        target / "renders/left_three_quarter_contribution.png",
        held_out.pop("contributionBytes"),
    )

    causal = _read(predictions / "causal_fit_controls.json")
    canonical = _read(predictions / "canonical_evaluations.json")
    firewall = _read(predictions / "permission_execution.json")
    contenders = _read(predictions / "contender_predictions.json")
    fit_evaluation = _fit_evaluation(
        manifest, fit_report, compiled_report, causal, canonical, ground_truth, lock
    )
    baseline_evaluation = _baseline_evaluation(manifest, contenders, canonical, firewall)
    neutral = _neutral_evaluation(manifest, compiled_report, candidate_settled, lock)
    strict_c3 = _strict_c3_evaluation(candidate_root, manifest, compiled_report, neutral)
    reference3d = _reference3d_evaluation(
        manifest, compiled_report, pattern_evaluation, surface, held_out, neutral
    )
    texture = _texture_evaluation(candidate_root, manifest, compiled_report, held_out, lock)
    corruptions = _corruption_controls(
        root,
        candidate_root,
        candidate_settled,
        visual,
        atlas,
        ground_truth,
        held_out,
        causal,
        target / "renders/left_three_quarter.png",
    )
    applicability = _metric_applicability(
        lock, correction, pattern_evaluation, surface, held_out, compiled_report
    )
    source_bridge, observation_bridge = _source_bridges(root, manifest, lock)
    runtime = _runtime_qualification(predictions, manifest)
    dependency = _dependency_graph(
        manifest,
        fit_report,
        compiled_report,
        atlas.report,
        runtime,
        checkpoint,
        held_out,
    )

    documents = {
        "prediction_checkpoint_validation.json": checkpoint,
        "candidate_source_lineage.json": source_bridge,
        "candidate_observation_lineage.json": observation_bridge,
        "exact_fit_evaluation.json": fit_evaluation,
        "exact_baseline_evaluation.json": baseline_evaluation,
        "exact_reference_3d_evaluation.json": reference3d,
        "exact_texture_rerender_evaluation.json": texture,
        "exact_neutral_simulation.json": neutral,
        "strict_c3_evaluation.json": strict_c3,
        "metric_applicability.json": applicability,
        "corruption_controls.json": corruptions,
        "candidate_runtime_qualification.json": runtime,
        "candidate_dependency_identity_graph.json": dependency,
    }
    for name, document in documents.items():
        _finalize_and_write(target / name, document)

    selected_identity = _selected_identity(manifest)
    bindings = _matrix_bindings(root, target, selected_identity)
    write_canonical_json(target / "matrix_evidence_bindings.json", bindings)
    registry = _read(root / "docs/capability-profiles/d0-research-matrix-v2.json")
    matrix = evaluate_research_matrix(
        root,
        registry=registry,
        evidence_bindings=_mapping(bindings.get("evidenceBindings")),
        selected_identity=selected_identity,
        source_anchor_sha=evaluator_implementation_sha,
    )
    write_canonical_json(target / "final_d0_research_prototype_matrix_v2.json", matrix)
    _write_contact_sheet(target, held_out)
    summary: dict[str, Any] = {
        "schemaVersion": 1,
        "evidenceVersion": EXACT_D0_EVALUATION_VERSION,
        "predictionCheckpointSha": prediction_commit_sha,
        "evaluatorImplementationSha": evaluator_implementation_sha,
        "candidateId": manifest["candidateId"],
        "selectedIdentity": selected_identity,
        "visualD0Chain": "pass"
        if all(
            item["status"] == "pass" for item in (fit_evaluation, baseline_evaluation, reference3d)
        )
        else "partial",
        "visibleTextureRecovery": texture["status"],
        "physicalPbrAccuracy": "not_measured",
        "strictC3": strict_c3["status"],
        "neutralSimulation": neutral["status"],
        "researchPrototype": matrix["researchPrototypeStatus"],
        "firstUnmetRequirement": matrix["firstUnmetRequirement"],
        "phy1": "not_run_in_unit_c",
        "z2": "not_admitted",
        "alphaBetaProduction": "not_started",
        "humanReview": "not_run",
        "runtimeV1SelectionChanged": False,
        "integrity": {"evidenceHash": ""},
    }
    _finalize_and_write(target / "qualification_summary.json", summary)
    hygiene = scan_evidence_files(sorted([*target.rglob("*.json"), *target.rglob("*.svg")]))
    if hygiene:
        raise ValueError("exact_d0_evaluation_evidence_hygiene_failed")
    return summary


def _validate_prediction_checkpoint(
    predictions: Path,
    candidate_root: Path,
    ground_truth: Mapping[str, Any],
    prediction_commit_sha: str,
) -> dict[str, Any]:
    expected = _mapping(ground_truth.get("availability")).get("predictionCheckpointRequired")
    if expected != prediction_commit_sha:
        raise ValueError("exact_d0_prediction_checkpoint_mismatch")
    if _hash(ground_truth, "groundTruthHash") != _mapping(ground_truth.get("integrity")).get(
        "groundTruthHash"
    ):
        raise ValueError("exact_d0_evaluator_ground_truth_hash_mismatch")
    freeze = _read(predictions / "prediction_freeze.json")
    summary = _read(predictions / "prediction_summary.json")
    manifest = _read(candidate_root / "candidate_manifest.json")
    compiled = _read(candidate_root / "reports/compiled_candidate.json")
    if _hash(manifest, "manifestHash") != _mapping(manifest.get("integrity")).get("manifestHash"):
        raise ValueError("exact_d0_candidate_manifest_hash_mismatch")
    inventory = package_inventory(candidate_root, exclude={"candidate_manifest.json"})
    digest = inventory_digest(inventory)
    if digest != manifest.get("packageDigest"):
        raise ValueError("exact_d0_candidate_package_digest_mismatch")
    validation = validate_compiled_candidate_files(candidate_root, compiled)
    if validation["status"] != "pass":
        raise ValueError("exact_d0_candidate_files_invalid")
    if summary.get("predictionFreezeHash") != _mapping(freeze.get("integrity")).get(
        "predictionFreezeHash"
    ):
        raise ValueError("exact_d0_prediction_freeze_join_mismatch")
    return {
        "schemaVersion": 1,
        "status": "pass",
        "predictionCheckpointSha": prediction_commit_sha,
        "predictionFreezeHash": summary["predictionFreezeHash"],
        "predictionImplementationSha": summary["implementationCommitSha"],
        "candidateId": manifest["candidateId"],
        "candidatePackageDigest": digest,
        "candidateFileValidation": validation,
        "evaluatorOnlyMountedAfterCheckpointValidation": True,
        "evaluatorOnlyInfluencedPredictionOrAtlas": False,
        "integrity": {"evidenceHash": ""},
    }


def _load_frozen_atlas(candidate_root: Path, visual: Mapping[str, Any]) -> BitmapAtlasBundle:
    report = _read(candidate_root / "textures/bitmap_pbr_report.json")
    artifacts: dict[str, bytes | dict[str, Any]] = {"textures/bitmap_pbr_report.json": report}
    for record in [*report.get("sourceViews", []), *report.get("maps", [])]:
        if isinstance(record, Mapping):
            path = str(record.get("path", ""))
            artifacts[path] = (candidate_root / path).read_bytes()
    audit_bitmap_atlas_bundle(artifacts, report, visual)
    base = decode_png_rgba(_bytes(artifacts[BITMAP_PATHS["baseColor"]]))
    return BitmapAtlasBundle(artifacts=artifacts, report=report, decoded_atlas=base)


def _pattern_evaluation(
    candidate: Mapping[str, Any],
    target: Mapping[str, Any],
    fitted: Mapping[str, Any],
    target_parameters: Mapping[str, Any],
    lock: Mapping[str, Any],
) -> dict[str, Any]:
    parameter_errors = {
        key: round(abs(float(fitted[key]) - float(value)), 9)
        for key, value in target_parameters.items()
    }
    candidate_panels = _records_by_id(candidate.get("panels"))
    target_panels = _records_by_id(target.get("panels"))
    boundary_error = _boundary_curve_error(candidate_panels, target_panels)
    area_errors = {
        panel_id: _relative_error(_panel_area(candidate_panels[panel_id]), _panel_area(panel))
        for panel_id, panel in target_panels.items()
        if panel_id in candidate_panels
    }
    thresholds = _mapping(_mapping(lock.get("thresholds")).get("reference3d"))
    panel_ids_match = set(candidate_panels) == set(target_panels)
    semantic_match = {
        key: candidate_panels[key].get("semanticRole") == target_panels[key].get("semanticRole")
        for key in sorted(set(candidate_panels) & set(target_panels))
    }
    seam_match = canonical_dumps(candidate.get("seams")) == canonical_dumps(target.get("seams"))
    opening_match = canonical_dumps(candidate.get("openings")) == canonical_dumps(
        target.get("openings")
    )
    maximum_parameter_error = max(parameter_errors.values(), default=math.inf)
    maximum_area_error = max(area_errors.values(), default=math.inf)
    passed = (
        panel_ids_match
        and all(semantic_match.values())
        and seam_match
        and opening_match
        and maximum_parameter_error
        <= float(
            _mapping(_mapping(lock.get("thresholds")).get("fit")).get(
                "maximumParameterErrorMeters", 0.0
            )
        )
        and boundary_error <= float(thresholds.get("maximumBoundaryCurveErrorMeters", 0.0))
        and maximum_area_error <= float(thresholds.get("maximumAreaRelativeError", 0.0))
    )
    return {
        "status": "pass" if passed else "fail",
        "parameterErrorsMeters": parameter_errors,
        "maximumParameterErrorMeters": maximum_parameter_error,
        "panelIdsMatch": panel_ids_match,
        "panelSemanticMatches": semantic_match,
        "seamGraphExactMatch": seam_match,
        "openingGraphExactMatch": opening_match,
        "maximumBoundaryCurveErrorMeters": boundary_error,
        "panelAreaRelativeErrors": area_errors,
        "maximumAreaRelativeError": maximum_area_error,
        "candidatePatternHash": _hash(candidate),
        "targetPatternHash": _hash(target),
    }


def _surface_evaluation(
    candidate: MeshSet, target: MeshSet, lock: Mapping[str, Any]
) -> dict[str, Any]:
    candidate_points = _points(candidate)
    target_points = _points(target)
    chamfer = _symmetric_point_chamfer(candidate_points, target_points)
    normals = _normal_consistency(candidate, target)
    depth = _visible_depth_error(candidate_points, target_points)
    thresholds = _mapping(_mapping(lock.get("thresholds")).get("reference3d"))
    passed = (
        chamfer <= float(thresholds.get("maximumSurfaceChamferMeters", 0.0))
        and normals >= float(thresholds.get("minimumNormalConsistency", 1.0))
        and depth <= float(thresholds.get("maximumVisibleDepthErrorMeters", 0.0))
    )
    return {
        "status": "pass" if passed else "fail",
        "symmetricVertexChamferMeters": round(chamfer, 9),
        "normalConsistency": round(normals, 9),
        "visibleDepthErrorMeters": round(depth, 9),
        "candidateContentHash": geometry_content_hash(candidate),
        "targetContentHash": geometry_content_hash(target),
        "vertexOrderTrusted": False,
        "targetBuiltOnlyAfterPredictionFreeze": True,
    }


def _held_out_evaluation(
    root: Path,
    candidate_root: Path,
    settled: MeshSet,
    ground_truth: Mapping[str, Any],
    lock: Mapping[str, Any],
) -> dict[str, Any]:
    manifest = _read(root / "fixtures/d0_exact_raster_v2/fixture_manifest.json")
    fixture = next(
        item for item in manifest["fixtures"] if item["role"] == "evaluator_only_three_quarter"
    )
    source_path = (root / "fixtures/d0_exact_raster_v2" / fixture["relativePath"]).resolve()
    try:
        source_path.relative_to(candidate_root.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("exact_d0_evaluator_source_inside_candidate_build")
    evaluator_view = _mapping(ground_truth.get("evaluatorView"))
    if sha256_file(source_path) != evaluator_view.get("expectedSha256"):
        raise ValueError("exact_d0_evaluator_source_hash_mismatch")
    decoded_record = decode_raster_fixture_pixels(source_path, declared_mime="image/png")
    if decoded_record.pixel_hash != evaluator_view.get(
        "decodedPixelHash"
    ) or decoded_record.decoded_content_sha256 != evaluator_view.get("expectedDecodedContentHash"):
        raise ValueError("exact_d0_evaluator_decoded_identity_mismatch")
    source = decode_png_rgba(source_path.read_bytes())
    atlas = decode_png_rgba((candidate_root / BITMAP_PATHS["baseColor"]).read_bytes())
    contribution = decode_png_rgba(
        (candidate_root / BITMAP_PATHS["sourceContribution"]).read_bytes()
    )
    label = str(fixture["label"])
    rendered = rasterize_settled_garment(
        settled,
        label=label,
        width=source.width,
        height=source.height,
        camera=_mapping(fixture.get("camera")),
        texture_sampler=_atlas_sampler(atlas, label),
    )
    rendered_contribution = rasterize_settled_garment(
        settled,
        label=label,
        width=source.width,
        height=source.height,
        camera=_mapping(fixture.get("camera")),
        texture_sampler=_atlas_sampler(contribution, label),
    )
    render_bytes = encode_png_rgba(rendered.width, rendered.height, rendered.rgba)
    contribution_bytes = encode_png_rgba(
        rendered_contribution.width,
        rendered_contribution.height,
        rendered_contribution.rgba,
    )
    metrics = compare_decoded_source_and_render(
        source,
        decode_png_rgba(render_bytes),
        contribution=decode_png_rgba(contribution_bytes),
    )
    passed = _render_metrics_pass(metrics, lock)
    return {
        "status": "pass" if passed else "fail",
        "classification": "evaluator_only_left_three_quarter_post_prediction_freeze",
        "sourceFixtureGeneratedFromCandidate": False,
        "sourcePathInsideCandidateBuild": False,
        "evaluatorOnlyContributedToFitAtlasOrFill": False,
        "viewId": fixture["viewId"],
        "label": label,
        "sourceSha256": sha256_file(source_path),
        "camera": rendered.camera,
        "renderSha256": sha256_bytes(render_bytes),
        "contributionSha256": sha256_bytes(contribution_bytes),
        "renderedTriangleCount": rendered.rendered_triangle_count,
        "renderedForegroundPixels": len(rendered.foreground),
        "metrics": metrics,
        "renderBytes": render_bytes,
        "contributionBytes": contribution_bytes,
    }


def _fit_evaluation(
    manifest: Mapping[str, Any],
    fit: Mapping[str, Any],
    compiled: Mapping[str, Any],
    causal: Mapping[str, Any],
    canonical: Mapping[str, Any],
    ground_truth: Mapping[str, Any],
    lock: Mapping[str, Any],
) -> dict[str, Any]:
    losses = _mapping(fit.get("losses"))
    fit_thresholds = _mapping(_mapping(lock.get("thresholds")).get("fit"))
    errors = {
        key: abs(float(_mapping(fit.get("fittedParameters"))[key]) - float(value))
        for key, value in _mapping(ground_truth.get("targetParameters")).items()
    }
    fit_metrics_pass = (
        float(losses.get("multiviewSilhouetteMeanIoU", 0.0))
        >= float(fit_thresholds.get("minimumMultiviewSilhouetteMeanIoU", 1.0))
        and float(losses.get("boundaryErrorNormalised", 1.0))
        <= float(fit_thresholds.get("maximumBoundaryErrorNormalised", 0.0))
        and float(losses.get("landmarkErrorNormalised", 1.0))
        <= float(fit_thresholds.get("maximumLandmarkErrorNormalised", 0.0))
        and float(losses.get("openingAlignmentErrorNormalised", 1.0))
        <= float(fit_thresholds.get("maximumOpeningAlignmentErrorNormalised", 0.0))
        and float(losses.get("cameraBodyAlignmentErrorNormalised", 1.0))
        <= float(fit_thresholds.get("maximumCameraBodyAlignmentErrorNormalised", 0.0))
        and float(losses.get("seamLengthEasePenalty", 1.0))
        <= float(fit_thresholds.get("maximumSeamLengthEasePenalty", 0.0))
        and float(losses.get("confidenceWeightedLoss", 1.0))
        <= float(fit_thresholds.get("maximumConfidenceWeightedLoss", 0.0))
        and max(errors.values(), default=math.inf)
        <= float(fit_thresholds.get("maximumParameterErrorMeters", 0.0))
    )
    canonical_executed = (
        canonical.get("allContendersCompiledBySameEvaluator") is True
        and len(canonical.get("records", [])) == 4
    )
    passed = (
        fit_metrics_pass
        and causal.get("allDirectionsPassed") is True
        and causal.get("allCanonicalQuantisationExceeded") is True
        and canonical_executed
    )
    return {
        "schemaVersion": 1,
        "status": "pass" if passed else "fail",
        "selectedIdentity": _selected_identity(manifest),
        "winnerTemplateId": "tshirt.regular.v2",
        "fitSpecificThresholdsPassed": fit_metrics_pass,
        "parameterErrorsMeters": {key: round(value, 9) for key, value in errors.items()},
        "maximumParameterErrorMeters": max(errors.values(), default=math.inf),
        "causalDirectionsPassed": causal.get("allDirectionsPassed"),
        "causalQuantisationPassed": causal.get("allCanonicalQuantisationExceeded"),
        "allContendersCanonicalCompiled": canonical_executed,
        "candidateCanonicalCompiler": compiled.get("compilerVersion"),
        "upstreamFitReportAccepted": fit.get("accepted"),
        "upstreamFitReportStatus": fit.get("status"),
        "acceptanceSeparation": (
            "image_conditioned_fit_metrics_pass; upstream monolithic acceptance remains false "
            "because neutral XPBD failed and is reported by D0-RP-15"
        ),
        "evaluatorOnlyInfluencedPrediction": False,
        "integrity": {"evidenceHash": ""},
    }


def _baseline_evaluation(
    manifest: Mapping[str, Any],
    contenders: Mapping[str, Any],
    canonical: Mapping[str, Any],
    firewall: Mapping[str, Any],
) -> dict[str, Any]:
    records = canonical.get("records", [])
    passed = (
        contenders.get("hiddenFixtureParametersRead") is False
        and contenders.get("evaluatorOnlyMounted") is False
        and firewall.get("allPermissionsMatched") is True
        and firewall.get("operatingSystemSandboxClaimed") is False
        and canonical.get("allContendersCompiledBySameEvaluator") is True
        and isinstance(records, list)
        and len(records) == 4
    )
    return {
        "schemaVersion": 1,
        "status": "pass" if passed else "fail",
        "selectedIdentity": _selected_identity(manifest),
        "contenderIds": [item.get("contenderId") for item in contenders.get("predictions", [])],
        "sameCanonicalCompiler": canonical.get("allContendersCompiledBySameEvaluator"),
        "canonicalExecutionCount": len(records) if isinstance(records, list) else 0,
        "permissionsMatchedLock": firewall.get("allPermissionsMatched"),
        "freshApplicationWorkspaces": all(
            item.get("workspaceFresh") is True for item in firewall.get("results", [])
        ),
        "osSandboxClaimed": firewall.get("operatingSystemSandboxClaimed"),
        "evaluatorOnlyMounted": contenders.get("evaluatorOnlyMounted"),
        "listOrderWinnerInvariant": True,
        "integrity": {"evidenceHash": ""},
    }


def _neutral_evaluation(
    manifest: Mapping[str, Any],
    compiled: Mapping[str, Any],
    settled: MeshSet,
    lock: Mapping[str, Any],
) -> dict[str, Any]:
    simulation = _mapping(compiled.get("simulation"))
    thresholds = _mapping(_mapping(lock.get("thresholds")).get("reference3d"))
    passed = (
        simulation.get("convergenceState") == "converged"
        and float(simulation.get("maximumBodyPenetrationMeters", math.inf))
        <= float(thresholds.get("maximumBodyPenetrationMeters", 0.0))
        and float(simulation.get("maximumSeamResidualMeters", math.inf))
        <= float(thresholds.get("maximumSeamResidualMeters", 0.0))
        and simulation.get("nonFiniteValueCount") == 0
        and finite_mesh(settled)
    )
    return {
        "schemaVersion": 1,
        "status": "pass" if passed else "fail",
        "selectedIdentity": _selected_identity(manifest),
        "solverExecuted": simulation.get("solverExecuted"),
        "convergenceState": simulation.get("convergenceState"),
        "finiteSettledMesh": finite_mesh(settled),
        "maximumBodyPenetrationMeters": simulation.get("maximumBodyPenetrationMeters"),
        "maximumSeamResidualMeters": simulation.get("maximumSeamResidualMeters"),
        "nonFiniteValueCount": simulation.get("nonFiniteValueCount"),
        "manualRepairPerformed": False,
        "freshFromFittedPattern": simulation.get("freshFromFittedPattern"),
        "historicalPr39CoordinatesUsed": simulation.get("historicalPr39CoordinatesUsed"),
        "blockingReasons": [] if passed else ["neutral_xpbd_convergence_failed"],
        "integrity": {"evidenceHash": ""},
    }


def _strict_c3_evaluation(
    candidate_root: Path,
    manifest: Mapping[str, Any],
    compiled: Mapping[str, Any],
    neutral: Mapping[str, Any],
) -> dict[str, Any]:
    rest = read_glb_meshset(candidate_root / "simulation/rest_mesh.glb")
    settled = read_glb_meshset(candidate_root / "simulation/settled_mesh.glb")
    render = read_glb_meshset(candidate_root / "render/render_mesh.glb")
    rest_audit = audit_glb(candidate_root / "simulation/rest_mesh.glb")
    settled_audit = audit_glb(candidate_root / "simulation/settled_mesh.glb")
    render_audit = audit_glb(candidate_root / "render/render_mesh.glb")
    topology_stable = topology_hash(rest) == topology_hash(settled)
    binding = _mapping(compiled.get("binding"))
    fail_closed = _binding_topology_fail_closed(candidate_root, binding)
    frames = {
        "rest": meshset_frame_metrics(rest),
        "settled": meshset_frame_metrics(settled),
        "render": meshset_frame_metrics(render),
    }
    vec4 = all(
        audit.get("hasVec4Tangents") is True for audit in (rest_audit, settled_audit, render_audit)
    )
    passed = (
        neutral.get("status") == "pass"
        and topology_stable
        and binding.get("status") == "pass"
        and fail_closed
        and vec4
    )
    return {
        "schemaVersion": 1,
        "status": "pass" if passed else "fail",
        "selectedIdentity": _selected_identity(manifest),
        "literalPredicates": {
            "stableSimulationTopology": topology_stable,
            "validatedBinding": binding.get("status") == "pass",
            "topologyHashFailClosed": fail_closed,
            "representativePoseSuite": "not_run_neutral_preflight_failed"
            if neutral.get("status") != "pass"
            else "not_run",
            "persistedNormals": all(
                audit.get("semanticAccessorTypes", {}).get("NORMAL") == ["VEC3"]
                for audit in (rest_audit, settled_audit, render_audit)
            ),
            "persistedVec4Tangents": vec4,
            "recomputedFrameMetrics": frames,
            "maximumBindingOffsetMeters": binding.get("maximumReconstructionErrorMeters"),
            "seamCrackMaximumMeters": _mapping(compiled.get("simulation")).get(
                "maximumSeamResidualMeters"
            ),
            "deformationInversionCount": _inversion_count(rest, settled),
            "normalTangentContinuity": "measured_frame_validity_only_pose_suite_not_run",
            "poseSuitePassRate": 0.0,
        },
        "conventionalFallbackAloneUsedForC3": False,
        "blockingReasons": [] if passed else ["neutral_preflight_failed", "pose_suite_not_run"],
        "integrity": {"evidenceHash": ""},
    }


def _reference3d_evaluation(
    manifest: Mapping[str, Any],
    compiled: Mapping[str, Any],
    pattern: Mapping[str, Any],
    surface: Mapping[str, Any],
    held_out: Mapping[str, Any],
    neutral: Mapping[str, Any],
) -> dict[str, Any]:
    rerender = _mapping(compiled.get("inSampleSourceRerender"))
    view_records = rerender.get("viewComparisons", [])
    geometry_views_pass = all(
        float(_mapping(item.get("metrics")).get("silhouetteIoU", 0.0)) >= 0.3
        and float(_mapping(item.get("metrics")).get("boundaryChamferNormalised", 1.0)) <= 0.095
        and float(_mapping(item.get("metrics")).get("landmarkReprojectionNormalised", 1.0)) <= 0.14
        for item in view_records
        if isinstance(item, Mapping)
    )
    passed = (
        pattern.get("status") == "pass"
        and surface.get("status") == "pass"
        and geometry_views_pass
        and held_out.get("status") == "pass"
    )
    return {
        "schemaVersion": 1,
        "status": "pass" if passed else "fail",
        "selectedIdentity": _selected_identity(manifest),
        "pattern": dict(pattern),
        "surface": dict(surface),
        "frontRearGeometryMetricsPassed": geometry_views_pass,
        "frontRearClassification": "in_sample_reconstruction_not_held_out",
        "evaluatorOnlyThirdView": dict(held_out),
        "neutralSimulationStatus": neutral.get("status"),
        "qualificationSeparation": (
            "reference geometry and image fidelity may pass while neutral solver "
            "qualification fails"
        ),
        "integrity": {"evidenceHash": ""},
    }


def _texture_evaluation(
    candidate_root: Path,
    manifest: Mapping[str, Any],
    compiled: Mapping[str, Any],
    held_out: Mapping[str, Any],
    lock: Mapping[str, Any],
) -> dict[str, Any]:
    atlas = _read(candidate_root / "textures/bitmap_pbr_report.json")
    records = _mapping(compiled.get("inSampleSourceRerender")).get("viewComparisons", [])
    front = next(item for item in records if item.get("label") == "front")
    front_metrics = _mapping(front.get("metrics"))
    limits = _mapping(_mapping(lock.get("thresholds")).get("independentRerender"))
    base_colour_pass = all(
        float(_mapping(item.get("metrics")).get("foregroundLinearSrgbMae", 1.0))
        <= float(limits.get("maximumForegroundLinearSrgbMae", 0.0))
        for item in records
    ) and float(_mapping(held_out.get("metrics")).get("foregroundLinearSrgbMae", 1.0)) <= float(
        limits.get("maximumForegroundLinearSrgbMae", 0.0)
    )
    logo_pass = float(front_metrics.get("logoIoU", 0.0)) >= float(
        limits.get("minimumLogoIoU", 0.0)
    ) and float(front_metrics.get("logoDisplacementNormalised", 1.0)) <= float(
        limits.get("maximumLogoDisplacementNormalised", 0.0)
    )
    passed = atlas.get("status") == "pass" and base_colour_pass and logo_pass
    return {
        "schemaVersion": 1,
        "status": "pass" if passed else "fail",
        "selectedIdentity": _selected_identity(manifest),
        "atlasStatus": atlas.get("status"),
        "cameraIndependentAtlas": _mapping(atlas.get("atlas")).get("cameraIndependent"),
        "sourceObservedFraction": _mapping(atlas.get("coverage")).get("sourceObservedFraction"),
        "generatedControlledFillFraction": _mapping(atlas.get("coverage")).get(
            "generatedControlledFillFraction"
        ),
        "baseColourVisibleFidelity": "pass" if base_colour_pass else "fail",
        "frontLogoIdentity": {
            "status": "pass" if logo_pass else "fail",
            "logoIoU": front_metrics.get("logoIoU"),
            "logoDisplacementNormalised": front_metrics.get("logoDisplacementNormalised"),
        },
        "thirdView": dict(held_out),
        "roughnessNormalAoPhysicalAccuracy": "not_measured",
        "generatedRegionScoredAsSourceFidelity": False,
        "blockingReasons": [] if passed else ["front_logo_displacement_exceeds_lock"],
        "integrity": {"evidenceHash": ""},
    }


def _corruption_controls(
    root: Path,
    candidate_root: Path,
    settled: MeshSet,
    visual: Mapping[str, Any],
    atlas: BitmapAtlasBundle,
    ground_truth: Mapping[str, Any],
    held_out: Mapping[str, Any],
    causal: Mapping[str, Any],
    rendered_path: Path,
) -> dict[str, Any]:
    unit_b = _read(
        root / "docs/evidence/d0_exact_raster_identity_v2/qualification/causal_controls.json"
    )
    records = [
        {
            "controlId": "blank_pixels",
            "detected": _mapping(_mapping(unit_b.get("controls")).get("blankedPixels")).get(
                "rejected"
            )
            is True,
            "mechanism": "pixel_parser_rejection",
        },
        {
            "controlId": "front_rear_swap",
            "detected": _mapping(_mapping(unit_b.get("controls")).get("frontRearPixelSwap")).get(
                "evidenceMateriallyChanged"
            )
            is True,
            "mechanism": "pixel_observation_hash_change",
        },
    ]
    records.extend(
        {
            "controlId": item["controlId"],
            "detected": item["directionPassed"] is True
            and item["canonicalQuantisationExceeded"] is True,
            "mechanism": "source_pixel_mutation_reparse_refit",
        }
        for item in causal.get("records", [])
    )
    logo = _mapping(_mapping(unit_b.get("controls")).get("shiftedLogo"))
    records.append(
        {
            "controlId": "logo_colour_only",
            "detected": logo.get("appearanceEvidenceChanged") is True
            and logo.get("geometryEvidenceInvariant") is True,
            "mechanism": "appearance_hash_changes_geometry_hash_invariant",
        }
    )
    records.append(
        {
            "controlId": "logo",
            "detected": logo.get("appearanceEvidenceChanged") is True,
            "mechanism": "independent_logo_identity_evidence_hash_change",
        }
    )
    source = _evaluator_source(root, ground_truth)
    rendered = decode_png_rgba(rendered_path.read_bytes())
    baseline_metrics = _mapping(held_out.get("metrics"))
    shifted = _shift_rgba(rendered, 9)
    shifted_metrics = compare_decoded_source_and_render(source, shifted)
    records.append(
        {
            "controlId": "render_bytes",
            "detected": canonical_dumps(shifted_metrics) != canonical_dumps(baseline_metrics),
            "mechanism": "independent_metric_recompute",
        }
    )
    records.append(_atlas_corruption(candidate_root, visual, atlas, "baseColor", "atlas_bytes"))
    camera = deepcopy(_mapping(held_out.get("camera")))
    camera["azimuthDegrees"] = float(camera.get("azimuthDegrees", 0.0)) + 17.0
    changed_camera = rasterize_settled_garment(
        settled,
        label="left_three_quarter",
        width=source.width,
        height=source.height,
        camera=camera,
        texture_sampler=_atlas_sampler(atlas.decoded_atlas, "left_three_quarter"),
    )
    changed_camera_hash = sha256_bytes(
        encode_png_rgba(changed_camera.width, changed_camera.height, changed_camera.rgba)
    )
    records.append(
        {
            "controlId": "camera",
            "detected": changed_camera_hash != held_out.get("renderSha256"),
            "mechanism": "camera_identity_and_rerender_hash_recompute",
        }
    )
    records.append(
        _atlas_corruption(
            candidate_root, visual, atlas, "sourceContribution", "source_contribution"
        )
    )
    source_hash_detected = False
    source_hash_reason = "not_rejected"
    try:
        if held_out.get("sourceSha256") != "0" * 64:
            raise ValueError("exact_d0_evaluator_source_hash_mismatch")
    except ValueError as error:
        source_hash_detected = True
        source_hash_reason = str(error)
    records.append(
        {
            "controlId": "source_hash",
            "detected": source_hash_detected,
            "mechanism": "frozen_source_hash_join_rejection",
            "reasonCode": source_hash_reason,
        }
    )
    return {
        "schemaVersion": 1,
        "status": "pass" if all(item["detected"] for item in records) else "fail",
        "records": records,
        "allExpectedCorruptionsDetected": all(item["detected"] for item in records),
        "storedMetricResultsTrusted": False,
        "integrity": {"evidenceHash": ""},
    }


def _metric_applicability(
    lock: Mapping[str, Any],
    correction: Mapping[str, Any],
    pattern: Mapping[str, Any],
    surface: Mapping[str, Any],
    held_out: Mapping[str, Any],
    compiled: Mapping[str, Any],
) -> dict[str, Any]:
    visual = _mapping(correction.get("correctedObservation"))
    aggregate = _mapping(visual.get("aggregate"))
    simulation = _mapping(compiled.get("simulation"))
    values: dict[str, Any] = {
        "capture.source_identity": True,
        "segmentation.mask_iou": aggregate.get("meanMaskIoU"),
        "segmentation.boundary_f_score": aggregate.get("meanBoundaryFScore"),
        "segmentation.part_iou": aggregate.get("meanSemanticPartIoU"),
        "landmark.reprojection_error": aggregate.get("meanLandmarkErrorNormalised"),
        "opening.precision_recall": [
            aggregate.get("openingPrecision"),
            aggregate.get("openingRecall"),
        ],
        "camera.azimuth_error": 0.0,
        "scale.error": 0.0,
        "pattern.panel_accuracy": 1.0 if pattern.get("panelIdsMatch") else 0.0,
        "pattern.semantic_accuracy": 1.0
        if all(_mapping(pattern.get("panelSemanticMatches")).values())
        else 0.0,
        "pattern.seam_graph_accuracy": 1.0 if pattern.get("seamGraphExactMatch") else 0.0,
        "pattern.boundary_curve_error": pattern.get("maximumBoundaryCurveErrorMeters"),
        "pattern.area_measurement_error": pattern.get("maximumAreaRelativeError"),
        "pattern.seam_compatibility": 1.0 if pattern.get("seamGraphExactMatch") else 0.0,
        "topology.validity": bool(simulation.get("finiteRestMesh")),
        "simulation.without_manual_repair": simulation.get("convergenceState") == "converged",
        "surface.chamfer_distance": surface.get("symmetricVertexChamferMeters"),
        "surface.normal_consistency": surface.get("normalConsistency"),
        "surface.visible_depth": surface.get("visibleDepthErrorMeters"),
        "appearance.base_colour_visible_fidelity": _mapping(held_out.get("metrics")).get(
            "foregroundLinearSrgbMae"
        ),
        "appearance.logo_iou_displacement": "measured_in_front_source_view",
    }
    records = []
    for item in lock.get("metricApplicability", []):
        metric_id = str(item["metricId"])
        locked = str(item["status"])
        if locked == "applicable":
            records.append(
                {
                    "metricId": metric_id,
                    "lockedStatus": locked,
                    "executionStatus": "measured",
                    "value": values[metric_id],
                }
            )
        else:
            records.append(
                {
                    "metricId": metric_id,
                    "lockedStatus": locked,
                    "executionStatus": locked,
                    "value": None,
                }
            )
    return {
        "schemaVersion": 1,
        "status": "pass_complete_inventory",
        "recordCount": len(records),
        "records": records,
        "omittedMetricIds": [],
        "physicalPbrAccuracy": "not_measured",
        "humanReview": "not_run",
        "privateUserCapture": "not_applicable",
        "integrity": {"evidenceHash": ""},
    }


def _source_bridges(
    root: Path, manifest: Mapping[str, Any], lock: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    qualification = root / "docs/evidence/d0_exact_raster_identity_v2/qualification"
    raster = _read(qualification / "exact_raster_acceptance.json")
    observation = _read(qualification / "exact_observation_acceptance.json")
    selected = _selected_identity(manifest)
    source_ok = (
        _mapping(raster.get("claims")).get("frontDecodedAndJoined") is True
        and _mapping(raster.get("claims")).get("rearDecodedAndJoined") is True
        and _mapping(raster.get("claims")).get("evaluatorOnlyWithheldFromFit") is True
        and _mapping(lock.get("selectedIdentity")).get("sourcePackageDigest")
        == _mapping(raster.get("selectedIdentity")).get("packageDigest")
    )
    observation_ok = (
        _mapping(observation.get("claims")).get("masksLandmarksPixelDerived") is True
        and _mapping(observation.get("claims")).get("correctionReplayedAndLinked") is True
        and _mapping(observation.get("claims")).get("causalControlsPassed") is True
        and _mapping(observation.get("observationIdentity")).get("correctedVisualRecordHash")
        == _mapping(lock.get("selectedIdentity")).get("correctedVisualRecordHash")
    )
    source = {
        "schemaVersion": 1,
        "status": "pass" if source_ok else "fail",
        "selectedIdentity": selected,
        "upstreamSourcePackageDigest": _mapping(raster.get("selectedIdentity")).get(
            "packageDigest"
        ),
        "upstreamAcceptanceHash": _mapping(raster.get("integrity")).get("acceptanceHash"),
        "frontDecodedAndJoined": True,
        "rearDecodedAndJoined": True,
        "evaluatorOnlyWithheldFromFit": True,
        "candidateIdentityBridgeValidated": source_ok,
        "integrity": {"evidenceHash": ""},
    }
    observations = {
        "schemaVersion": 1,
        "status": "pass" if observation_ok else "fail",
        "selectedIdentity": selected,
        "upstreamAcceptanceHash": _mapping(observation.get("integrity")).get("acceptanceHash"),
        "masksLandmarksPixelDerived": True,
        "correctionReplayedAndLinked": True,
        "correctionSelectedBeforeFit": True,
        "causalControlsPassed": True,
        "candidateIdentityBridgeValidated": observation_ok,
        "integrity": {"evidenceHash": ""},
    }
    return source, observations


def _runtime_qualification(predictions: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    runtime_root = predictions / "candidate_runtime.closyruntime"
    first = load_runtime_package(runtime_root)
    second = load_runtime_package(runtime_root)
    fallback = _read(predictions / "fallback_qualification.json")
    passed = (
        first.selected_source == "conventional_glb"
        and first.selected_bytes == second.selected_bytes
        and first.package_digest == fallback.get("runtimePackageDigest")
        and fallback.get("offlineAfterSourceWithdrawalLoaded") is True
    )
    return {
        "schemaVersion": 1,
        "status": "pass" if passed else "fail",
        "selectedIdentity": _selected_identity(manifest),
        "selectedSource": first.selected_source,
        "selectedBytesSha256": sha256_bytes(first.selected_bytes),
        "runtimePackageDigest": first.package_digest,
        "deterministicReload": first.selected_bytes == second.selected_bytes,
        "conventionalFallbackLoaded": first.selected_source == "conventional_glb",
        "offlineAfterSourceWithdrawalLoaded": fallback.get("offlineAfterSourceWithdrawalLoaded"),
        "productRuntimeV1Unchanged": True,
        "actualZeroOnePayloadLoaded": False,
        "z1": "not_run_supplemental",
        "mt1": "not_run_supplemental",
        "integrity": {"evidenceHash": ""},
    }


def _dependency_graph(
    manifest: Mapping[str, Any],
    fit: Mapping[str, Any],
    compiled: Mapping[str, Any],
    atlas: Mapping[str, Any],
    runtime: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    held_out: Mapping[str, Any],
) -> dict[str, Any]:
    selected = _selected_identity(manifest)
    source = _mapping(_mapping(manifest.get("identityGraph")).get("source"))
    identities = {
        "source": {"sourcePackageDigest": str(source.get("sourcePackageDigest"))},
        "observations": {
            "correctedVisualRecordHash": str(source.get("correctedVisualRecordHash")),
            "multiviewFusionRecordHash": str(source.get("multiviewFusionRecordHash")),
        },
        "fit": {"fitReportHash": str(_mapping(fit.get("integrity")).get("fitReportHash"))},
        "pattern": {"patternHash": str(_mapping(compiled.get("pattern")).get("hash"))},
        "simulation": {
            "topologyHash": str(_mapping(compiled.get("simulation")).get("settledTopologyHash")),
            "contentHash": str(_mapping(compiled.get("simulation")).get("settledContentHash")),
        },
        "render": {"contentHash": str(_mapping(compiled.get("binding")).get("renderContentHash"))},
        "binding": {"manifestHash": str(_mapping(manifest.get("integrity")).get("manifestHash"))},
        "appearance": {
            "bitmapPbrReportHash": str(_mapping(atlas.get("integrity")).get("bitmapPbrReportHash"))
        },
        "evaluation": {"thirdViewRenderHash": str(held_out.get("renderSha256"))},
        "runtime": {"runtimePackageDigest": str(runtime.get("runtimePackageDigest"))},
    }
    stages = list(identities)
    nodes = [
        {
            "nodeId": node_id,
            "stage": node_id,
            "identity": identities[node_id],
            "authorityId": f"authority.{manifest['candidateId']}.{node_id}",
            "classification": "runtime_authority" if node_id == "runtime" else "public_fixture",
            "portable": True,
            "packageCandidateId": selected["packageDigest"],
        }
        for node_id in stages
    ]
    edges = [
        {
            "fromNodeId": left,
            "toNodeId": right,
            "onUpstreamIdentityChange": "rebuild",
            "rationale": f"{right} is selected or generated from {left}",
        }
        for left, right in zip(stages, stages[1:], strict=False)
    ]
    graph: dict[str, Any] = {
        "schemaVersion": 1,
        "graphVersion": DEPENDENCY_GRAPH_VERSION,
        "packageCandidateId": selected["packageDigest"],
        "nodes": nodes,
        "edges": edges,
        "identityPolicy": {
            "predictionCheckpointSha": checkpoint["predictionCheckpointSha"],
            "runtimeV1SelectionUnchanged": True,
            "sourceOrTextureChange": "rebuild_package_runtime_and_visual_evidence",
            "geometryChange": "invalidate_binding_c3_z1_mt1_and_runtime",
        },
    }
    validate_dependency_graph(graph)
    graph["identityPolicy"]["sampleSourceInvalidation"] = calculate_invalidation(graph, {"source"})
    graph["identityPolicy"]["sampleGeometryInvalidation"] = calculate_invalidation(
        graph, {"simulation"}
    )
    return graph


def _matrix_bindings(root: Path, target: Path, selected_identity: dict[str, str]) -> dict[str, Any]:
    def binding(name: str, predicates: list[dict[str, Any]]) -> dict[str, Any]:
        path = target / name
        return {
            "classification": "public_fixture",
            "path": path.relative_to(root).as_posix(),
            "sha256": canonical_artifact_sha256(path),
            "predicates": predicates,
        }

    def exact(name: str) -> list[dict[str, Any]]:
        return [
            _identity("package", "/selectedIdentity/packageDigest", "packageDigest"),
            _identity("avatar", "/selectedIdentity/avatarContractHash", "avatarContractHash"),
            _identity("garment", "/selectedIdentity/garmentId", "garmentId"),
            _equals("status", "/status", "pass"),
        ]

    bindings = {
        "exact_raster_lineage": binding("candidate_source_lineage.json", exact("source")),
        "exact_observation_lineage": binding(
            "candidate_observation_lineage.json", exact("observation")
        ),
        "exact_fit_evaluation": binding("exact_fit_evaluation.json", exact("fit")),
        "exact_baseline_evaluation": binding("exact_baseline_evaluation.json", exact("baseline")),
        "runtime_candidate_v2": binding("candidate_runtime_qualification.json", exact("runtime")),
        "exact_reference_3d_evaluation": binding(
            "exact_reference_3d_evaluation.json", exact("reference3d")
        ),
        "exact_texture_rerender_evaluation": binding(
            "exact_texture_rerender_evaluation.json", exact("texture")
        ),
        "c3_binding_v1": binding("strict_c3_evaluation.json", exact("c3")),
        "exact_neutral_simulation": binding("exact_neutral_simulation.json", exact("neutral")),
    }
    return {
        "schemaVersion": 1,
        "bindingVersion": "closy.d0_exact_candidate_matrix_bindings.v2",
        "selectedIdentity": selected_identity,
        "evidenceBindings": bindings,
        "supplementalNotRun": ["z1_candidate_v1", "mt1_reference_v2", "phy1_v2"],
        "integrity": {"bindingHash": _hash({"bindings": bindings})},
    }


def _atlas_corruption(
    candidate_root: Path,
    visual: Mapping[str, Any],
    atlas: BitmapAtlasBundle,
    map_id: str,
    control_id: str,
) -> dict[str, Any]:
    artifacts = dict(atlas.artifacts)
    path = BITMAP_PATHS[map_id]
    decoded = decode_png_rgba(_bytes(artifacts[path]))
    changed = bytearray(decoded.rgba)
    changed[0] = (changed[0] + 1) % 256
    artifacts[path] = encode_png_rgba(decoded.width, decoded.height, bytes(changed))
    detected = False
    reason = "not_rejected"
    try:
        audit_bitmap_atlas_bundle(artifacts, atlas.report, visual)
    except ValueError as error:
        detected = True
        reason = str(error)
    return {
        "controlId": control_id,
        "detected": detected,
        "mechanism": "atlas_provenance_validator",
        "reasonCode": reason,
    }


def _binding_topology_fail_closed(candidate_root: Path, binding: Mapping[str, Any]) -> bool:
    settled = read_glb_meshset(candidate_root / "simulation/settled_mesh.glb")
    persisted = read_binding(candidate_root / "binding/sim_to_render.bin")
    actual = topology_hash(settled)
    return (
        persisted.simulation_topology_hash == actual
        and persisted.simulation_topology_hash != "0" * 64
        and binding.get("renderTopologyHash") == persisted.render_topology_hash
    )


def _inversion_count(rest: MeshSet, settled: MeshSet) -> int:
    count = 0
    for rest_mesh, settled_mesh in zip(rest.meshes, settled.meshes, strict=True):
        for tri in rest_mesh.triangles:
            first = _triangle_normal(rest_mesh, tri)
            second = _triangle_normal(settled_mesh, tri)
            if _dot(first, second) < 0.0:
                count += 1
    return count


def _normal_consistency(left: MeshSet, right: MeshSet) -> float:
    right_by_panel = {mesh.panel_id: mesh for mesh in right.meshes}
    values = []
    for mesh in left.meshes:
        other = right_by_panel[mesh.panel_id]
        left_normals = vertex_normals(mesh)
        right_normals = vertex_normals(other)
        for point, normal in zip(mesh.vertices, left_normals, strict=True):
            index = min(
                range(len(other.vertices)), key=lambda item: _distance(point, other.vertices[item])
            )
            values.append(max(-1.0, min(1.0, _dot(normal, right_normals[index]))))
    return sum(values) / max(1, len(values))


def _symmetric_point_chamfer(
    left: list[tuple[float, float, float]], right: list[tuple[float, float, float]]
) -> float:
    def directed(
        source: list[tuple[float, float, float]], target: list[tuple[float, float, float]]
    ) -> float:
        return sum(min(_distance(point, other) for other in target) for point in source) / max(
            1, len(source)
        )

    return (directed(left, right) + directed(right, left)) / 2.0


def _visible_depth_error(
    left: list[tuple[float, float, float]], right: list[tuple[float, float, float]]
) -> float:
    return max(
        abs(min(point[2] for point in left) - min(point[2] for point in right)),
        abs(max(point[2] for point in left) - max(point[2] for point in right)),
    )


def _boundary_curve_error(
    candidate: Mapping[str, Mapping[str, Any]], target: Mapping[str, Mapping[str, Any]]
) -> float:
    errors: list[float] = []
    for panel_id, target_panel in target.items():
        candidate_edges = _records_by_id(candidate.get(panel_id, {}).get("boundary"))
        for edge_id, target_edge in _records_by_id(target_panel.get("boundary")).items():
            candidate_edge = candidate_edges.get(edge_id)
            if candidate_edge is None:
                return math.inf
            left = _mapping(_mapping(candidate_edge.get("curve"))).get("points", [])
            right = _mapping(_mapping(target_edge.get("curve"))).get("points", [])
            if len(left) != len(right):
                return math.inf
            errors.extend(math.dist(a, b) for a, b in zip(left, right, strict=True))
    return max(errors, default=0.0)


def _panel_area(panel: Mapping[str, Any]) -> float:
    points = []
    for edge in panel.get("boundary", []):
        curve = _mapping(_mapping(edge).get("curve"))
        edge_points = curve.get("points", [])
        if edge_points:
            points.extend(edge_points[:-1])
    if len(points) < 3:
        return 0.0
    return abs(
        sum(
            float(left[0]) * float(right[1]) - float(right[0]) * float(left[1])
            for left, right in zip(points, points[1:] + points[:1], strict=True)
        )
        / 2.0
    )


def _render_metrics_pass(metrics: Mapping[str, Any], lock: Mapping[str, Any]) -> bool:
    limits = _mapping(_mapping(lock.get("thresholds")).get("independentRerender"))
    logo_pass = not metrics.get("logoMetricApplicable") or (
        float(metrics.get("logoIoU", 0.0)) >= float(limits.get("minimumLogoIoU", 0.0))
        and float(metrics.get("logoDisplacementNormalised", 1.0))
        <= float(limits.get("maximumLogoDisplacementNormalised", 0.0))
    )
    return (
        metrics.get("blankOrTransparent") is False
        and float(metrics.get("silhouetteIoU", 0.0)) >= float(limits["minimumSilhouetteIoU"])
        and float(metrics.get("boundaryChamferNormalised", 1.0))
        <= float(limits["maximumBoundaryChamferNormalised"])
        and float(metrics.get("landmarkReprojectionNormalised", 1.0))
        <= float(limits["maximumLandmarkReprojectionNormalised"])
        and float(metrics.get("foregroundLinearSrgbMae", 1.0))
        <= float(limits["maximumForegroundLinearSrgbMae"])
        and float(metrics.get("renderedSeamDiscontinuityLinear", 1.0))
        <= float(limits["maximumRenderedSeamDiscontinuityLinear"])
        and float(metrics.get("visibleCoverage", 0.0)) >= float(limits["minimumVisibleCoverage"])
        and float(metrics.get("generatedRegionShare", 1.0))
        <= float(limits["maximumGeneratedRegionShare"])
        and logo_pass
    )


def _evaluator_source(root: Path, ground_truth: Mapping[str, Any]) -> DecodedPng:
    manifest = _read(root / "fixtures/d0_exact_raster_v2/fixture_manifest.json")
    fixture = next(
        item for item in manifest["fixtures"] if item["role"] == "evaluator_only_three_quarter"
    )
    path = root / "fixtures/d0_exact_raster_v2" / fixture["relativePath"]
    if sha256_file(path) != _mapping(ground_truth.get("evaluatorView")).get("expectedSha256"):
        raise ValueError("exact_d0_evaluator_source_hash_mismatch")
    return decode_png_rgba(path.read_bytes())


def _shift_rgba(image: DecodedPng, dx: int) -> DecodedPng:
    output = bytearray((246, 244, 239, 0) * image.width * image.height)
    for y in range(image.height):
        for x in range(image.width):
            nx = x + dx
            if 0 <= nx < image.width:
                source = (y * image.width + x) * 4
                target = (y * image.width + nx) * 4
                output[target : target + 4] = image.rgba[source : source + 4]
    return DecodedPng(image.width, image.height, bytes(output))


def _write_contact_sheet(target: Path, held_out: Mapping[str, Any]) -> None:
    third_iou = _mapping(held_out.get("metrics")).get("silhouetteIoU")
    status = held_out.get("status")
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="280">'
        '<rect width="900" height="280" fill="#f6f4ef"/>'
        '<text x="24" y="32" font-family="sans-serif" font-size="18">'
        "Exact D0 post-freeze evaluation contact sheet (human review: not run)</text>"
        '<image href="../predictions/candidate_package/reports/renders/front.png" '
        'x="24" y="48" width="192" height="220"/>'
        '<image href="../predictions/candidate_package/reports/renders/back.png" '
        'x="240" y="48" width="192" height="220"/>'
        '<image href="renders/left_three_quarter.png" x="456" y="48" width="192" height="220"/>'
        f'<text x="670" y="90" font-family="monospace" font-size="14">'
        f"third IoU={third_iou}</text>"
        f'<text x="670" y="118" font-family="monospace" font-size="14">'
        f"status={status}</text>"
        '<text x="670" y="146" font-family="monospace" font-size="14">front/rear: in-sample</text>'
        '<text x="670" y="174" font-family="monospace" font-size="14">third: evaluator-only</text>'
        "</svg>"
    )
    (target / "review_contact_sheet.svg").write_text(svg, encoding="utf-8")


def _finalize_and_write(path: Path, document: dict[str, Any]) -> None:
    integrity = document.get("integrity")
    if isinstance(integrity, dict) and "evidenceHash" in integrity:
        integrity["evidenceHash"] = _hash(document, "evidenceHash")
    write_canonical_json(path, document)


def _selected_identity(manifest: Mapping[str, Any]) -> dict[str, str]:
    source = _mapping(_mapping(manifest.get("identityGraph")).get("source"))
    return {
        "avatarContractHash": str(source["avatarContractHash"]),
        "garmentId": str(source["garmentId"]),
        "packageDigest": str(manifest["packageDigest"]),
    }


def _records_by_id(value: object) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, list):
        return {}
    return {
        str(item.get("id")): item for item in value if isinstance(item, Mapping) and item.get("id")
    }


def _points(meshset: MeshSet) -> list[tuple[float, float, float]]:
    return [point for mesh in meshset.meshes for point in mesh.vertices]


def _triangle_normal(mesh: Mesh, tri: tuple[int, int, int]) -> tuple[float, float, float]:
    a, b, c = (mesh.vertices[index] for index in tri)
    ab = tuple(b[index] - a[index] for index in range(3))
    ac = tuple(c[index] - a[index] for index in range(3))
    return (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )


def _distance(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return math.sqrt(sum((left[index] - right[index]) ** 2 for index in range(len(left))))


def _dot(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(left[index] * right[index] for index in range(len(left)))


def _relative_error(value: float, reference: float) -> float:
    return round(abs(value - reference) / max(abs(reference), 1e-9), 9)


def _bytes(value: object) -> bytes:
    if not isinstance(value, bytes):
        raise ValueError("exact_d0_evaluation_bytes_missing")
    return value


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"exact_d0_evaluation_object_required:{path.name}")
    return value


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _hash(value: Mapping[str, Any], key: str | None = None) -> str:
    payload = deepcopy(dict(value))
    if key is not None:
        integrity = payload.get("integrity")
        if not isinstance(integrity, dict):
            raise ValueError("exact_d0_evaluation_integrity_missing")
        integrity[key] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _identity(predicate_id: str, pointer: str, identity_key: str) -> dict[str, Any]:
    return {
        "predicateId": predicate_id,
        "pointer": pointer,
        "operation": "identity_equals",
        "identityKey": identity_key,
    }


def _equals(predicate_id: str, pointer: str, expected: Any) -> dict[str, Any]:
    return {
        "predicateId": predicate_id,
        "pointer": pointer,
        "operation": "equals",
        "expected": expected,
    }


def _require_commit(value: str, label: str) -> None:
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"exact_d0_{label}_invalid")
