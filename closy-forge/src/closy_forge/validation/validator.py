from __future__ import annotations

import math
import tempfile
from pathlib import Path
from typing import Any

from closy_forge.appearance import hash_texture_identity_report
from closy_forge.binding.binary_format import read_binding, write_binding
from closy_forge.binding.production_binding import (
    build_production_binding_c3_report_from_package,
    hash_production_binding_c3_report,
    hash_production_binding_contract,
)
from closy_forge.binding.reconstruct import reconstruct_vertices, reconstruction_error
from closy_forge.capture.source_records import hash_capture_record
from closy_forge.contracts.avatar import REQUIRED_BODY_REGIONS, REQUIRED_LANDMARKS
from closy_forge.contracts.common import COORDINATE_CONVENTION
from closy_forge.contracts.semantic import REQUIRED_OPENINGS, REQUIRED_PANELS, REQUIRED_SEAMS
from closy_forge.fitting import hash_tshirt_fit_report
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.geometry.curves import sample_curve
from closy_forge.geometry.glb_io import audit_glb, write_indexed_glb
from closy_forge.geometry.mesh_model import (
    Mesh,
    MeshSet,
    Tri,
    Vec2,
    Vec3,
    cross,
    finite_mesh,
    sub,
)
from closy_forge.geometry.triangulation import validate_panel_boundary
from closy_forge.inspection import (
    hash_inspection_artifact_manifest,
    hash_inspection_artifact_report,
)
from closy_forge.inspection.deterministic_renderer import required_artifact_specs
from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import (
    geometry_content_hash,
    sha256_bytes,
    sha256_file,
    topology_hash,
)
from closy_forge.package_io.paths import validate_package_relpath
from closy_forge.proposals import (
    CLEAN_ACCEPTANCE_GATE_REJECTION_REASONS,
    PARTIAL_BINDING_VALIDATION_REJECTION_REASONS,
    PARTIAL_CLEANUP_REJECTION_REASONS,
    PARTIAL_REPAIR_RESULT_REJECTION_REASONS,
    PARTIAL_REPAIR_RETOPOLOGY_PLAN_REJECTION_REASONS,
    PARTIAL_RUNTIME_BINDING_RESULT_REJECTION_REASONS,
    PARTIAL_SEMANTIC_TRANSFER_REJECTION_REASONS,
    REQUIRED_CLEAN_REJECTION_REASONS,
    build_geometry_binding_candidate_report,
    build_geometry_binding_validation_report,
    build_geometry_clean_acceptance_gate_report,
    build_geometry_cleanup_plan,
    build_geometry_cleanup_result,
    build_geometry_material_uv_transfer_report,
    build_geometry_repair_result_report,
    build_geometry_repair_retopology_plan,
    build_geometry_runtime_binding_result_report,
    build_geometry_semantic_transfer_report,
    build_geometry_visual_shell_review_report,
    build_proposal_runtime_binding,
    build_proposal_runtime_render_mesh,
    build_raw_geometry_topology_report,
    build_stitched_shell_assets,
    hash_clean_geometry_proposal,
    hash_geometry_binding_candidate_report,
    hash_geometry_binding_validation_report,
    hash_geometry_clean_acceptance_gate,
    hash_geometry_cleanup_plan,
    hash_geometry_cleanup_result,
    hash_geometry_material_uv_transfer,
    hash_geometry_proposal,
    hash_geometry_repair_result,
    hash_geometry_repair_retopology_plan,
    hash_geometry_runtime_binding_result,
    hash_geometry_semantic_transfer_report,
    hash_geometry_stitched_shell_report,
    hash_geometry_visual_shell_review,
    hash_provider_bakeoff_report,
    hash_provider_registry,
    hash_raw_geometry_topology_report,
    hash_stitched_analysis_shell,
    reproject_cleanup_preview_to_settled_simulation,
)
from closy_forge.rendering import (
    build_render_frame_pose_suite_report,
    hash_render_frame_pose_suite_report,
)
from closy_forge.simulation.self_collision import (
    build_self_collision_report,
    hash_self_collision_report,
)
from closy_forge.validation.issues import Severity, ValidationIssue
from closy_forge.visual_understanding import (
    REQUIRED_TSHIRT_VISUAL_LANDMARKS,
    hash_correction_record,
    hash_fused_evidence,
    hash_multiview_fusion_record,
    hash_visual_observations,
)

EXPECTED_FILES = [
    "manifest.json",
    "provenance.json",
    "source/capture_record.json",
    "source/capture_quality.json",
    "source/visual_observations.json",
    "source/correction_record.json",
    "source/multiview_fusion.json",
    "fitting/tshirt_fit.json",
    "textures/texture_identity.json",
    "textures/source_projection.json",
    "textures/generated_atlas.json",
    "textures/pbr_material_maps.json",
    "textures/conventional_fallback_materials.json",
    "proposals/raw_geometry_proposal.json",
    "proposals/manual_raw_visual_proposal.glb",
    "proposals/manual_cleanup_preview.glb",
    "proposals/manual_repair_preview.glb",
    "proposals/manual_runtime_retopology_preview.glb",
    "proposals/clean_geometry_proposal.json",
    "proposals/provider_registry.json",
    "avatar/avatar_contract.json",
    "avatar/reference_avatar.glb",
    "avatar/collision.glb",
    "avatar/body_regions.json",
    "semantic/garment_graph.json",
    "semantic/confidence.json",
    "pattern/pattern.json",
    "pattern/panels.svg",
    "simulation/simulation_mesh.glb",
    "simulation/mesh_manifest.json",
    "simulation/constraints.json",
    "simulation/rest_state.json",
    "simulation/settled_state.json",
    "simulation/settle_diagnostics.json",
    "simulation/material_physics.json",
    "stitch/logical_stitched_analysis_shell.json",
    "render/fallback.glb",
    "render/stitched_shell.glb",
    "render/mesh_manifest.json",
    "render/materials.json",
    "binding/sim_to_render.bin",
    "binding/binding_manifest.json",
    "binding/production_binding_contract.json",
    "binding/proposal_sim_to_render.bin",
    "binding/proposal_binding_manifest.json",
    "reports/avatar_quality.json",
    "reports/capture_quality.json",
    "reports/visual_understanding_quality.json",
    "reports/multiview_fusion_quality.json",
    "reports/fitting_quality.json",
    "reports/texture_quality.json",
    "reports/geometry_proposal_quality.json",
    "reports/raw_geometry_topology.json",
    "reports/provider_bakeoff.json",
    "reports/geometry_cleanup_plan.json",
    "reports/geometry_cleanup_result.json",
    "reports/geometry_semantic_transfer.json",
    "reports/geometry_binding_candidate.json",
    "reports/geometry_binding_validation.json",
    "reports/geometry_repair_retopology_plan.json",
    "reports/geometry_repair_result.json",
    "reports/geometry_runtime_binding_result.json",
    "reports/geometry_material_uv_transfer.json",
    "reports/geometry_stitched_shell.json",
    "reports/geometry_visual_shell_review.json",
    "reports/render_frame_pose_suite.json",
    "reports/production_binding_c3.json",
    "reports/self_collision_report.json",
    "reports/inspection/manifest.json",
    "reports/inspection/inspection_report.json",
    "reports/inspection/pattern_panels_labels.svg",
    "reports/inspection/rest_simulation_mesh_front.svg",
    "reports/inspection/rest_simulation_mesh_side_depth.svg",
    "reports/inspection/settled_garment_on_avatar_front.svg",
    "reports/inspection/canonical_render_shell_front.svg",
    "reports/inspection/manual_raw_proposal_front.svg",
    "reports/inspection/cleanup_preview_front.svg",
    "reports/inspection/repair_preview_front.svg",
    "reports/inspection/runtime_bound_preview_front.svg",
    "reports/inspection/logical_stitched_candidate_front.svg",
    "reports/inspection/render_split_stitched_candidate_front.svg",
    "reports/inspection/topology_problem_overlay_front.svg",
    "reports/geometry_clean_acceptance_gate.json",
    "reports/clean_geometry_proposal_quality.json",
    "reports/provider_registry_quality.json",
    "reports/semantic_quality.json",
    "reports/pattern_quality.json",
    "reports/simulation_quality.json",
    "reports/render_quality.json",
    "reports/binding_quality.json",
    "reports/package_validation.json",
    "reports/summary.json",
    "reports/summary.md",
]


def validate_package(package_dir: Path) -> dict[str, Any]:
    issues: list[ValidationIssue] = []
    if package_dir.suffix != ".closygarment":
        issues.append(
            _issue("package_suffix_invalid", "fatal", ".", "Package must end with .closygarment.")
        )
        return _report(issues)
    manifest_path = package_dir / "manifest.json"
    if not manifest_path.exists():
        issues.append(
            _issue("manifest_missing", "fatal", "manifest.json", "Missing top-level manifest.")
        )
        return _report(issues)
    try:
        manifest = read_json(manifest_path)
    except Exception as exc:
        issues.append(_issue("manifest_unreadable", "fatal", "manifest.json", str(exc)))
        return _report(issues)
    _validate_required_files(package_dir, issues)
    if manifest.get("schemaVersion") != 1:
        issues.append(
            _issue(
                "unsupported_schema_version",
                "fatal",
                "manifest.json",
                "Only schemaVersion 1 is supported.",
            )
        )
    if manifest.get("packageKind") != "closy.garment":
        issues.append(
            _issue(
                "package_kind_invalid",
                "fatal",
                "manifest.json",
                "packageKind must be closy.garment.",
            )
        )
    if manifest.get("garmentClass") != "tshirt":
        issues.append(
            _issue(
                "unsupported_garment_class",
                "fatal",
                "manifest.json",
                "Implementation 01 only supports tshirt.",
            )
        )
    if manifest.get("units") != "metres":
        issues.append(
            _issue(
                "coordinate_units_invalid",
                "fatal",
                "manifest.json",
                "Forge packages must use metres.",
            )
        )
    if manifest.get("coordinateConvention", {}).get("id") != COORDINATE_CONVENTION["id"]:
        issues.append(
            _issue(
                "coordinate_convention_invalid",
                "fatal",
                "manifest.json",
                "Unexpected coordinate convention.",
            )
        )

    inventory = manifest.get("inventory", [])
    if not isinstance(inventory, list):
        issues.append(
            _issue("inventory_invalid", "fatal", "manifest.json", "inventory must be a list.")
        )
        inventory = []
    inventory_paths: set[str] = set()
    for entry in inventory:
        if not isinstance(entry, dict):
            continue
        rel = str(entry.get("path", ""))
        if rel == "manifest.json":
            issues.append(
                _issue(
                    "manifest_self_hash_cycle",
                    "fatal",
                    rel,
                    "manifest.json must not be inventoried.",
                )
            )
        if rel in inventory_paths:
            issues.append(
                _issue("duplicate_inventory_path", "fatal", rel, "Inventory paths must be unique.")
            )
        inventory_paths.add(rel)
        try:
            validate_package_relpath(rel)
        except ValueError:
            issues.append(
                _issue(
                    "unsafe_package_path",
                    "fatal",
                    rel or "manifest.json",
                    "Inventory path is unsafe.",
                )
            )
            continue
        file_path = package_dir / rel
        if file_path.is_symlink():
            try:
                file_path.resolve().relative_to(package_dir.resolve())
            except ValueError:
                issues.append(
                    _issue("escaping_symlink", "fatal", rel, "Symlink escapes package root.")
                )
        if not file_path.exists():
            issues.append(
                _issue("missing_declared_file", "fatal", rel, "Declared file is missing.")
            )
            continue
        if entry.get("byteSize") != file_path.stat().st_size:
            issues.append(
                _issue("file_size_mismatch", "fatal", rel, "Declared byte size does not match.")
            )
        if entry.get("sha256") != sha256_file(file_path):
            issues.append(
                _issue("file_hash_mismatch", "fatal", rel, "Declared SHA-256 does not match.")
            )

    _validate_avatar(package_dir, issues)
    _validate_capture(package_dir, manifest, issues)
    _validate_visual_understanding(package_dir, manifest, issues)
    _validate_multiview_fusion(package_dir, manifest, issues)
    _validate_fitting(package_dir, manifest, issues)
    _validate_texture_identity(package_dir, manifest, issues)
    _validate_geometry_proposal(package_dir, manifest, issues)
    _validate_raw_geometry_topology(package_dir, manifest, issues)
    _validate_provider_bakeoff(package_dir, manifest, issues)
    _validate_geometry_cleanup_plan(package_dir, manifest, issues)
    _validate_geometry_cleanup_result(package_dir, manifest, issues)
    _validate_geometry_semantic_transfer(package_dir, manifest, issues)
    _validate_geometry_binding_candidate(package_dir, manifest, issues)
    _validate_geometry_binding_validation(package_dir, manifest, issues)
    _validate_geometry_repair_retopology_plan(package_dir, manifest, issues)
    _validate_geometry_repair_result(package_dir, manifest, issues)
    _validate_geometry_runtime_binding_result(package_dir, manifest, issues)
    _validate_geometry_material_uv_transfer(package_dir, manifest, issues)
    _validate_geometry_stitched_shell(package_dir, manifest, issues)
    _validate_geometry_visual_shell_review(package_dir, manifest, issues)
    _validate_render_frame_pose_suite(package_dir, manifest, issues)
    _validate_production_binding_contract(package_dir, manifest, issues)
    _validate_production_binding_c3(package_dir, manifest, issues)
    _validate_inspection_artifacts(package_dir, manifest, issues)
    _validate_geometry_clean_acceptance_gate(package_dir, manifest, issues)
    _validate_provider_registry(package_dir, manifest, issues)
    _validate_clean_geometry_proposal(package_dir, manifest, issues)
    _validate_semantic(package_dir, issues)
    _validate_pattern(package_dir, issues)
    _validate_meshes_and_constraints(package_dir, issues)
    _validate_settle_state(package_dir, manifest, issues)
    _validate_self_collision_report(package_dir, manifest, issues)
    _validate_glbs(package_dir, issues)
    _validate_binding(package_dir, issues)
    _validate_capabilities(manifest, issues)
    return _report(issues)


def _validate_avatar(package_dir: Path, issues: list[ValidationIssue]) -> None:
    avatar = _read_required_json(package_dir, "avatar/avatar_contract.json", issues)
    if avatar is None:
        return
    landmarks = avatar.get("landmarks", {})
    for landmark in REQUIRED_LANDMARKS:
        if landmark not in landmarks:
            issues.append(
                _issue(
                    "required_landmark_missing",
                    "fatal",
                    "avatar/avatar_contract.json",
                    "Required avatar landmark missing.",
                    landmark,
                )
            )
    regions_doc = _read_required_json(package_dir, "avatar/body_regions.json", issues)
    if regions_doc is None:
        return
    regions = regions_doc.get("regions", [])
    region_ids = {region.get("id") for region in regions}
    for region in REQUIRED_BODY_REGIONS:
        if region not in region_ids:
            issues.append(
                _issue(
                    "required_body_region_missing",
                    "fatal",
                    "avatar/body_regions.json",
                    "Required body region missing.",
                    region,
                )
            )
    if avatar.get("heightMeters") is None or not 1.70 <= float(avatar["heightMeters"]) <= 1.86:
        issues.append(
            _issue(
                "avatar_height_invalid",
                "fatal",
                "avatar/avatar_contract.json",
                "Reference avatar height must be approximately human scale.",
            )
        )


def _validate_capture(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    capture_record = _read_required_json(package_dir, "source/capture_record.json", issues)
    capture_quality = _read_required_json(package_dir, "source/capture_quality.json", issues)
    if capture_record is None or capture_quality is None:
        return
    privacy = capture_record.get("privacy", {})
    if not isinstance(privacy, dict):
        issues.append(
            _issue(
                "capture_privacy_policy_invalid",
                "fatal",
                "source/capture_record.json",
                "Capture record privacy block must be an object.",
            )
        )
        privacy = {}
    if (
        privacy.get("containsUserImagery") is not False
        or privacy.get("containsPersonalBodyData") is not False
    ):
        issues.append(
            _issue(
                "capture_user_data_in_fixture",
                "fatal",
                "source/capture_record.json",
                "Phase 2 fixture capture records must not contain user imagery or body data.",
            )
        )
    if (
        privacy.get("allowExternalApis") is not False
        or privacy.get("allowTrainingUse") is not False
    ):
        issues.append(
            _issue(
                "capture_provider_policy_violation",
                "fatal",
                "source/capture_record.json",
                "Synthetic fixture capture cannot permit external API use or training use.",
            )
        )
    session = capture_record.get("captureSession", {})
    if not isinstance(session, dict):
        issues.append(
            _issue(
                "capture_session_invalid",
                "fatal",
                "source/capture_record.json",
                "Capture session must be an object.",
            )
        )
        session = {}
    if session.get("runtimeExternalApis") is not False:
        issues.append(
            _issue(
                "capture_provider_policy_violation",
                "fatal",
                "source/capture_record.json",
                "Synthetic fixture capture must be generated without runtime external APIs.",
            )
        )
    views = capture_record.get("views", [])
    if not isinstance(views, list):
        issues.append(
            _issue(
                "capture_views_invalid",
                "fatal",
                "source/capture_record.json",
                "Capture views must be a list.",
            )
        )
        views = []
    if len(views) < 4:
        issues.append(
            _issue(
                "capture_view_count_too_low",
                "fatal",
                "source/capture_record.json",
                "Synthetic T-shirt fixture must include at least four view records.",
            )
        )
    if _int_or(session.get("viewCount"), -1) != len(views):
        issues.append(
            _issue(
                "capture_view_count_mismatch",
                "fatal",
                "source/capture_record.json",
                "Capture session viewCount must match the number of view records.",
            )
        )
    immutability = capture_record.get("immutability", {})
    if not isinstance(immutability, dict):
        issues.append(
            _issue(
                "capture_immutability_invalid",
                "fatal",
                "source/capture_record.json",
                "Capture record immutability block must be an object.",
            )
        )
        immutability = {}
    declared_hash = immutability.get("sourceRecordHash")
    if declared_hash != hash_capture_record(capture_record):
        issues.append(
            _issue(
                "capture_record_hash_mismatch",
                "fatal",
                "source/capture_record.json",
                "Capture record hash must match its canonical payload.",
            )
        )
    if capture_quality.get("sourceRecordId") != capture_record.get("recordId"):
        issues.append(
            _issue(
                "capture_quality_source_mismatch",
                "fatal",
                "source/capture_quality.json",
                "Capture quality report must reference the capture record ID.",
            )
        )
    if capture_quality.get("sourceRecordHash") != declared_hash:
        issues.append(
            _issue(
                "capture_quality_source_hash_mismatch",
                "fatal",
                "source/capture_quality.json",
                "Capture quality report must reference the capture record hash.",
            )
        )
    if capture_quality.get("overallStatus") != "pass":
        issues.append(
            _issue(
                "capture_quality_not_pass",
                "fatal",
                "source/capture_quality.json",
                "Capture quality report must pass for this canonical fixture.",
            )
        )
    if _float_or(capture_quality.get("overallScore"), 0.0) < _float_or(
        capture_quality.get("qualityThreshold"), 1.0
    ):
        issues.append(
            _issue(
                "capture_quality_below_threshold",
                "fatal",
                "source/capture_quality.json",
                "Capture quality score is below the declared threshold.",
            )
        )
    if _int_or(capture_quality.get("viewCount"), -1) != len(views):
        issues.append(
            _issue(
                "capture_quality_view_count_mismatch",
                "fatal",
                "source/capture_quality.json",
                "Capture quality viewCount must match the source record.",
            )
        )
    policy = capture_quality.get("policy", {})
    if not isinstance(policy, dict):
        issues.append(
            _issue(
                "capture_quality_policy_invalid",
                "fatal",
                "source/capture_quality.json",
                "Capture quality policy block must be an object.",
            )
        )
        policy = {}
    if (
        policy.get("externalApiUseAllowed") is not False
        or policy.get("trainingUseAllowed") is not False
    ):
        issues.append(
            _issue(
                "capture_quality_policy_violation",
                "fatal",
                "source/capture_quality.json",
                "Capture quality report cannot permit external API or training use.",
            )
        )
    caps = manifest.get("capabilities", {})
    if not isinstance(caps, dict):
        return
    if caps.get("sourceCaptureRecordAvailable") is not True:
        issues.append(
            _issue(
                "source_capture_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest must declare available immutable synthetic capture records.",
            )
        )
    if caps.get("captureQualityScored") is not True:
        issues.append(
            _issue(
                "capture_quality_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest must declare deterministic capture quality scoring.",
            )
        )
    if _contains_nonfinite(capture_record) or _contains_nonfinite(capture_quality):
        issues.append(
            _issue(
                "capture_nonfinite_numeric_value",
                "fatal",
                "source/capture_record.json",
                "Capture records and quality reports must not contain NaN or Infinity.",
            )
        )


def _validate_visual_understanding(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    capture_record = _read_required_json(package_dir, "source/capture_record.json", issues)
    visual = _read_required_json(package_dir, "source/visual_observations.json", issues)
    correction = _read_required_json(package_dir, "source/correction_record.json", issues)
    if capture_record is None or visual is None or correction is None:
        return
    declared_capture_hash = _nested_string(capture_record, ["immutability", "sourceRecordHash"], "")
    if visual.get("sourceRecordId") != capture_record.get("recordId"):
        issues.append(
            _issue(
                "visual_observation_source_mismatch",
                "fatal",
                "source/visual_observations.json",
                "Visual observations must reference the capture record ID.",
            )
        )
    if visual.get("sourceRecordHash") != declared_capture_hash:
        issues.append(
            _issue(
                "visual_observation_source_hash_mismatch",
                "fatal",
                "source/visual_observations.json",
                "Visual observations must reference the capture record hash.",
            )
        )
    if _nested_string(visual, ["integrity", "visualRecordHash"], "") != hash_visual_observations(
        visual
    ):
        issues.append(
            _issue(
                "visual_observation_hash_mismatch",
                "fatal",
                "source/visual_observations.json",
                "Visual observation hash must match its canonical payload.",
            )
        )
    provider = visual.get("provider", {})
    if not isinstance(provider, dict):
        issues.append(
            _issue(
                "visual_provider_invalid",
                "fatal",
                "source/visual_observations.json",
                "Visual observation provider must be an object.",
            )
        )
        provider = {}
    if provider.get("externalApis") is not False or provider.get("trainingUse") is not False:
        issues.append(
            _issue(
                "visual_provider_policy_violation",
                "fatal",
                "source/visual_observations.json",
                "Synthetic visual observations cannot use external APIs or training use.",
            )
        )
    views = visual.get("views", [])
    if not isinstance(views, list):
        issues.append(
            _issue(
                "visual_observation_views_invalid",
                "fatal",
                "source/visual_observations.json",
                "Visual observation views must be a list.",
            )
        )
        views = []
    capture_view_ids = {
        str(view.get("viewId"))
        for view in capture_record.get("views", [])
        if isinstance(view, dict)
    }
    visual_view_ids = {str(view.get("viewId")) for view in views if isinstance(view, dict)}
    if visual_view_ids != capture_view_ids:
        issues.append(
            _issue(
                "visual_observation_view_set_mismatch",
                "fatal",
                "source/visual_observations.json",
                "Visual observations must cover the same capture views.",
            )
        )
    mask_count = 0
    observed_landmarks: set[str] = set()
    for view in views:
        if not isinstance(view, dict):
            continue
        masks = view.get("masks", [])
        if not isinstance(masks, list):
            issues.append(
                _issue(
                    "visual_mask_list_invalid",
                    "fatal",
                    "source/visual_observations.json",
                    "Each visual observation view must contain a mask list.",
                    str(view.get("viewId", "")),
                )
            )
            masks = []
        mask_count += len(masks)
        for mask in masks:
            if isinstance(mask, dict):
                _validate_normalised_mask(mask, issues)
        landmarks = view.get("landmarks", [])
        if not isinstance(landmarks, list):
            issues.append(
                _issue(
                    "visual_landmark_list_invalid",
                    "fatal",
                    "source/visual_observations.json",
                    "Each visual observation view must contain a landmark list.",
                    str(view.get("viewId", "")),
                )
            )
            landmarks = []
        for landmark in landmarks:
            if isinstance(landmark, dict):
                observed_landmarks.add(str(landmark.get("id", "")))
                _validate_normalised_point(
                    landmark.get("position2d"), "visual_landmark_out_of_range", issues
                )
    if mask_count < len(views):
        issues.append(
            _issue(
                "visual_mask_missing",
                "fatal",
                "source/visual_observations.json",
                "Each capture view must include at least one target-garment mask.",
            )
        )
    for landmark_id in REQUIRED_TSHIRT_VISUAL_LANDMARKS:
        if landmark_id not in observed_landmarks:
            issues.append(
                _issue(
                    "required_tshirt_visual_landmark_missing",
                    "fatal",
                    "source/visual_observations.json",
                    "Required T-shirt visual landmark missing.",
                    landmark_id,
                )
            )
    declared_visual_hash = _nested_string(visual, ["integrity", "visualRecordHash"], "")
    if correction.get("visualUnderstandingId") != visual.get("visualUnderstandingId"):
        issues.append(
            _issue(
                "correction_visual_id_mismatch",
                "fatal",
                "source/correction_record.json",
                "Correction record must reference the visual observation ID.",
            )
        )
    if correction.get("visualRecordHash") != declared_visual_hash:
        issues.append(
            _issue(
                "correction_visual_hash_mismatch",
                "fatal",
                "source/correction_record.json",
                "Correction record must reference the visual observation hash.",
            )
        )
    if _nested_string(
        correction, ["integrity", "correctionRecordHash"], ""
    ) != hash_correction_record(correction):
        issues.append(
            _issue(
                "correction_record_hash_mismatch",
                "fatal",
                "source/correction_record.json",
                "Correction record hash must match its canonical payload.",
            )
        )
    correction_privacy = correction.get("privacy", {})
    if not isinstance(correction_privacy, dict):
        issues.append(
            _issue(
                "correction_privacy_policy_invalid",
                "fatal",
                "source/correction_record.json",
                "Correction privacy block must be an object.",
            )
        )
        correction_privacy = {}
    if (
        correction_privacy.get("allowExternalApis") is not False
        or correction_privacy.get("allowTrainingUse") is not False
    ):
        issues.append(
            _issue(
                "correction_policy_violation",
                "fatal",
                "source/correction_record.json",
                "Correction records cannot permit external API or training use.",
            )
        )
    caps = manifest.get("capabilities", {})
    if not isinstance(caps, dict):
        return
    for key, code in [
        ("visualObservationsAvailable", "visual_observations_capability_missing"),
        ("garmentMaskAvailable", "garment_mask_capability_missing"),
        ("garmentLandmarksAvailable", "garment_landmarks_capability_missing"),
        ("editableCorrectionRecordAvailable", "correction_record_capability_missing"),
    ]:
        if caps.get(key) is not True:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "manifest.json",
                    f"Manifest capability {key} must be true for this fixture.",
                )
            )
    if _contains_nonfinite(visual) or _contains_nonfinite(correction):
        issues.append(
            _issue(
                "visual_observation_nonfinite_numeric_value",
                "fatal",
                "source/visual_observations.json",
                "Visual observations and correction records must not contain NaN or Infinity.",
            )
        )


def _validate_multiview_fusion(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    capture_record = _read_required_json(package_dir, "source/capture_record.json", issues)
    visual = _read_required_json(package_dir, "source/visual_observations.json", issues)
    correction = _read_required_json(package_dir, "source/correction_record.json", issues)
    fusion = _read_required_json(package_dir, "source/multiview_fusion.json", issues)
    quality = _read_required_json(package_dir, "reports/multiview_fusion_quality.json", issues)
    if (
        capture_record is None
        or visual is None
        or correction is None
        or fusion is None
        or quality is None
    ):
        return
    capture_hash = _nested_string(capture_record, ["immutability", "sourceRecordHash"], "")
    visual_hash = _nested_string(visual, ["integrity", "visualRecordHash"], "")
    correction_hash = _nested_string(correction, ["integrity", "correctionRecordHash"], "")
    corrected_hash = _nested_string(
        correction, ["application", "afterVisualRecordHash"], visual_hash
    )
    if fusion.get("sourceRecordHash") != capture_hash:
        issues.append(
            _issue(
                "multiview_capture_hash_mismatch",
                "fatal",
                "source/multiview_fusion.json",
                "Multiview fusion must reference the capture record hash.",
            )
        )
    if fusion.get("sourceVisualRecordHash") != visual_hash:
        issues.append(
            _issue(
                "multiview_visual_hash_mismatch",
                "fatal",
                "source/multiview_fusion.json",
                "Multiview fusion must reference the visual record hash.",
            )
        )
    if fusion.get("sourceCorrectionRecordHash") != correction_hash:
        issues.append(
            _issue(
                "multiview_correction_hash_mismatch",
                "fatal",
                "source/multiview_fusion.json",
                "Multiview fusion must reference the correction record hash.",
            )
        )
    if fusion.get("sourceCorrectedVisualRecordHash") != corrected_hash:
        issues.append(
            _issue(
                "multiview_corrected_visual_hash_mismatch",
                "fatal",
                "source/multiview_fusion.json",
                "Multiview fusion must reference the corrected visual hash.",
            )
        )
    if _nested_string(
        fusion, ["integrity", "multiviewFusionRecordHash"], ""
    ) != hash_multiview_fusion_record(fusion):
        issues.append(
            _issue(
                "multiview_fusion_hash_mismatch",
                "fatal",
                "source/multiview_fusion.json",
                "Multiview fusion hash must match its canonical payload.",
            )
        )
    required_pairs = fusion.get("viewPairing", {}).get("requiredPairs", [])
    if (
        not isinstance(required_pairs, list)
        or not required_pairs
        or required_pairs[0].get("status") != "pass"
    ):
        issues.append(
            _issue(
                "multiview_front_rear_pair_missing",
                "fatal",
                "source/multiview_fusion.json",
                "BP51 requires a passing front/rear capture pair.",
            )
        )
    quality_gate = fusion.get("qualityGate", {})
    if _nested_string(fusion, ["qualityGate", "status"], "") != "passed_d0_synthetic":
        issues.append(
            _issue(
                "multiview_quality_gate_not_passed",
                "fatal",
                "source/multiview_fusion.json",
                "BP51 D0 synthetic multiview quality gate must pass before fitting.",
            )
        )
    if quality_gate.get("readiness", {}).get("expensiveDownstreamAllowed") is not True:
        issues.append(
            _issue(
                "multiview_downstream_gate_closed",
                "fatal",
                "source/multiview_fusion.json",
                "Multiview fusion must explicitly allow downstream fitting for this fixture.",
            )
        )
    fused = fusion.get("fusedEvidence", {})
    if not isinstance(fused, dict):
        fused = {}
    if len(fused.get("masks", [])) < 4 or len(fused.get("landmarks", [])) < 10:
        issues.append(
            _issue(
                "multiview_fused_evidence_incomplete",
                "fatal",
                "source/multiview_fusion.json",
                "Fused masks and landmarks are incomplete.",
            )
        )
    if quality.get("fusionRecordId") != fusion.get("fusionRecordId"):
        issues.append(
            _issue(
                "multiview_quality_source_mismatch",
                "fatal",
                "reports/multiview_fusion_quality.json",
                "Multiview quality report must reference the fusion record.",
            )
        )
    if _contains_nonfinite(fusion):
        issues.append(
            _issue(
                "multiview_fusion_nonfinite_numeric_value",
                "fatal",
                "source/multiview_fusion.json",
                "Multiview fusion record must not contain NaN or Infinity.",
            )
        )
    caps = manifest.get("capabilities", {})
    if not isinstance(caps, dict):
        return
    for key, code in [
        ("frontRearCapturePairingAvailable", "front_rear_pairing_capability_missing"),
        ("viewOrientationScaleEvidenceAvailable", "orientation_scale_capability_missing"),
        ("crossViewGarmentIdentityAvailable", "cross_view_identity_capability_missing"),
        ("semanticIdentityTrackingAvailable", "semantic_identity_capability_missing"),
        ("multiviewVisualFusionAvailable", "multiview_fusion_capability_missing"),
        ("phase2QualityGateAvailable", "phase2_quality_gate_capability_missing"),
        ("multiviewCorrectionReplayAvailable", "multiview_correction_capability_missing"),
        ("phase2ResumeCacheAvailable", "phase2_resume_cache_capability_missing"),
    ]:
        if caps.get(key) is not True:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "manifest.json",
                    f"Manifest capability {key} must be true for this fixture.",
                )
            )


def _validate_fitting(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    visual = _read_required_json(package_dir, "source/visual_observations.json", issues)
    fusion = _read_required_json(package_dir, "source/multiview_fusion.json", issues)
    fit_report = _read_required_json(package_dir, "fitting/tshirt_fit.json", issues)
    if visual is None or fusion is None or fit_report is None:
        return
    declared_visual_hash = _nested_string(visual, ["integrity", "visualRecordHash"], "")
    declared_fusion_hash = _nested_string(
        fusion,
        ["integrity", "multiviewFusionRecordHash"],
        "",
    )
    declared_fused_hash = hash_fused_evidence(fusion.get("fusedEvidence", {}))
    if fit_report.get("sourceVisualUnderstandingId") != visual.get("visualUnderstandingId"):
        issues.append(
            _issue(
                "fitting_visual_id_mismatch",
                "fatal",
                "fitting/tshirt_fit.json",
                "Fit report must reference the visual observation ID.",
            )
        )
    if fit_report.get("sourceVisualRecordHash") != declared_visual_hash:
        issues.append(
            _issue(
                "fitting_visual_hash_mismatch",
                "fatal",
                "fitting/tshirt_fit.json",
                "Fit report must reference the visual observation hash.",
            )
        )
    if fit_report.get("sourceMultiviewFusionId") != fusion.get("fusionRecordId"):
        issues.append(
            _issue(
                "fitting_multiview_fusion_id_mismatch",
                "fatal",
                "fitting/tshirt_fit.json",
                "BP52 fit report must reference the multiview fusion record ID.",
            )
        )
    if fit_report.get("sourceMultiviewFusionHash") != declared_fusion_hash:
        issues.append(
            _issue(
                "fitting_multiview_fusion_hash_mismatch",
                "fatal",
                "fitting/tshirt_fit.json",
                "BP52 fit report must reference the multiview fusion record hash.",
            )
        )
    if fit_report.get("sourceFusedEvidenceHash") != declared_fused_hash:
        issues.append(
            _issue(
                "fitting_fused_evidence_hash_mismatch",
                "fatal",
                "fitting/tshirt_fit.json",
                "BP52 fit report must reference the fused visual evidence hash.",
            )
        )
    if fit_report.get("sourceCorrectedVisualRecordHash") != fusion.get(
        "sourceCorrectedVisualRecordHash"
    ):
        issues.append(
            _issue(
                "fitting_corrected_visual_hash_mismatch",
                "fatal",
                "fitting/tshirt_fit.json",
                "BP52 fit report must reference the corrected visual record hash.",
            )
        )
    if _nested_string(fit_report, ["integrity", "fitReportHash"], "") != hash_tshirt_fit_report(
        fit_report
    ):
        issues.append(
            _issue(
                "tshirt_fit_hash_mismatch",
                "fatal",
                "fitting/tshirt_fit.json",
                "Fit report hash must match its canonical payload.",
            )
        )
    if fit_report.get("status") != "pass" or fit_report.get("accepted") is not True:
        issues.append(
            _issue(
                "tshirt_fit_not_accepted",
                "fatal",
                "fitting/tshirt_fit.json",
                "T-shirt fit report must pass and be accepted for this fixture.",
            )
        )
    fitted_parameters = fit_report.get("fittedParameters", {})
    if not isinstance(fitted_parameters, dict):
        issues.append(
            _issue(
                "tshirt_fit_parameters_invalid",
                "fatal",
                "fitting/tshirt_fit.json",
                "Fit report fittedParameters must be an object.",
            )
        )
    else:
        try:
            TShirtParameters(
                **{key: float(value) for key, value in fitted_parameters.items()}
            ).validate()
        except (TypeError, ValueError) as exc:
            issues.append(
                _issue(
                    "tshirt_fit_parameters_invalid",
                    "fatal",
                    "fitting/tshirt_fit.json",
                    str(exc),
                )
            )
    losses = fit_report.get("losses", {})
    thresholds = fit_report.get("thresholds", {})
    if not isinstance(losses, dict) or not isinstance(thresholds, dict):
        issues.append(
            _issue(
                "tshirt_fit_loss_invalid",
                "fatal",
                "fitting/tshirt_fit.json",
                "Fit report losses and thresholds must be objects.",
            )
        )
    else:
        if _float_or(losses.get("landmarkRmsNormalised"), 1.0) > _float_or(
            thresholds.get("maximumLandmarkRmsNormalised"), 0.0
        ):
            issues.append(
                _issue(
                    "tshirt_fit_landmark_loss_too_high",
                    "fatal",
                    "fitting/tshirt_fit.json",
                    "Landmark RMS exceeds fit threshold.",
                )
            )
        if _float_or(losses.get("maskWidthErrorMeters"), 1.0) > _float_or(
            thresholds.get("maximumMaskWidthErrorMeters"), 0.0
        ):
            issues.append(
                _issue(
                    "tshirt_fit_mask_loss_too_high",
                    "fatal",
                    "fitting/tshirt_fit.json",
                    "Mask width error exceeds fit threshold.",
                )
            )
        if _float_or(losses.get("maximumParameterDeltaMeters"), 1.0) > _float_or(
            thresholds.get("maximumParameterDeltaMeters"), 0.0
        ):
            issues.append(
                _issue(
                    "tshirt_fit_parameter_delta_too_high",
                    "fatal",
                    "fitting/tshirt_fit.json",
                    "Parameter delta exceeds fit threshold.",
                )
            )
        if _float_or(losses.get("multiviewSilhouetteMeanIoU"), 0.0) < _float_or(
            thresholds.get("minimumMultiviewSilhouetteMeanIoU"), 1.0
        ):
            issues.append(
                _issue(
                    "tshirt_fit_multiview_silhouette_too_low",
                    "fatal",
                    "fitting/tshirt_fit.json",
                    "Multiview silhouette IoU is below fit threshold.",
                )
            )
        for loss_key, threshold_key, code, message in [
            (
                "boundaryErrorNormalised",
                "maximumBoundaryErrorNormalised",
                "tshirt_fit_boundary_error_too_high",
                "Boundary error exceeds fit threshold.",
            ),
            (
                "landmarkErrorNormalised",
                "maximumLandmarkErrorNormalised",
                "tshirt_fit_landmark_error_too_high",
                "Landmark error exceeds fit threshold.",
            ),
            (
                "openingAlignmentErrorNormalised",
                "maximumOpeningAlignmentErrorNormalised",
                "tshirt_fit_opening_alignment_too_high",
                "Opening alignment error exceeds fit threshold.",
            ),
            (
                "cameraBodyAlignmentErrorNormalised",
                "maximumCameraBodyAlignmentErrorNormalised",
                "tshirt_fit_camera_alignment_too_high",
                "Camera/body alignment error exceeds fit threshold.",
            ),
            (
                "seamLengthEasePenalty",
                "maximumSeamLengthEasePenalty",
                "tshirt_fit_seam_ease_penalty_too_high",
                "Seam/length/ease penalty exceeds fit threshold.",
            ),
            (
                "parameterErrorMeters",
                "maximumParameterErrorMeters",
                "tshirt_fit_parameter_error_too_high",
                "Independent parameter error exceeds fit threshold.",
            ),
            (
                "confidenceWeightedLoss",
                "maximumConfidenceWeightedLoss",
                "tshirt_fit_confidence_weighted_loss_too_high",
                "Confidence-weighted fit loss exceeds fit threshold.",
            ),
        ]:
            if _float_or(losses.get(loss_key), 1.0) > _float_or(thresholds.get(threshold_key), 0.0):
                issues.append(_issue(code, "fatal", "fitting/tshirt_fit.json", message))
    evidence_separation = fit_report.get("evidenceSeparation", {})
    if (
        not isinstance(evidence_separation, dict)
        or evidence_separation.get("expectedParametersFromFixtureSource") is not False
    ):
        issues.append(
            _issue(
                "tshirt_fit_evidence_separation_missing",
                "fatal",
                "fitting/tshirt_fit.json",
                "BP52 fit must separate observed evidence from prior/fixture parameters.",
            )
        )
    else:
        observed_evidence = evidence_separation.get("observedEvidence", [])
        if not isinstance(observed_evidence, list) or len(observed_evidence) < 2:
            issues.append(
                _issue(
                    "tshirt_fit_observed_evidence_incomplete",
                    "fatal",
                    "fitting/tshirt_fit.json",
                    "BP52 fit must list visual and fused observed evidence.",
                )
            )
    if not isinstance(fit_report.get("boundedParameterSpace"), dict):
        issues.append(
            _issue(
                "tshirt_fit_bounded_parameter_space_missing",
                "fatal",
                "fitting/tshirt_fit.json",
                "BP52 fit must declare bounded T-shirt parameter space.",
            )
        )
    trace = fit_report.get("optimizationTrace", [])
    if not isinstance(trace, list) or len(trace) < 4:
        issues.append(
            _issue(
                "tshirt_fit_optimization_trace_incomplete",
                "fatal",
                "fitting/tshirt_fit.json",
                "BP52 fit must include an iterative optimisation trace.",
            )
        )
    convergence = fit_report.get("convergence", {})
    if not isinstance(convergence, dict) or convergence.get("status") != "converged_d0_synthetic":
        issues.append(
            _issue(
                "tshirt_fit_not_converged",
                "fatal",
                "fitting/tshirt_fit.json",
                "BP52 fit convergence diagnostics must report D0 convergence.",
            )
        )
    alternatives = fit_report.get("alternatives", [])
    if not isinstance(alternatives, list) or len(alternatives) < 2:
        issues.append(
            _issue(
                "tshirt_fit_alternatives_missing",
                "fatal",
                "fitting/tshirt_fit.json",
                "BP52 fit must include multiple hypotheses for ambiguous evidence.",
            )
        )
    held_out = fit_report.get("heldOutEvaluation", {})
    if not isinstance(held_out, dict) or held_out.get("status") != "pass":
        issues.append(
            _issue(
                "tshirt_fit_held_out_evaluation_failed",
                "fatal",
                "fitting/tshirt_fit.json",
                "BP52 fit must pass held-out view evaluation for this fixture.",
            )
        )
    perturbation = fit_report.get("perturbationEvaluation", {})
    if not isinstance(perturbation, dict) or perturbation.get("status") != "pass":
        issues.append(
            _issue(
                "tshirt_fit_perturbation_evaluation_failed",
                "fatal",
                "fitting/tshirt_fit.json",
                "BP52 fit must pass deterministic perturbation evaluation.",
            )
        )
    settled = fit_report.get("settledRenderComparison", {})
    if not isinstance(settled, dict) or "status" not in settled:
        issues.append(
            _issue(
                "tshirt_fit_settled_render_comparison_status_missing",
                "fatal",
                "fitting/tshirt_fit.json",
                "BP52 fit must report settled-render/drape comparison status truthfully.",
            )
        )
    caps = manifest.get("capabilities", {})
    if not isinstance(caps, dict):
        return
    if caps.get("tshirtParameterFitAvailable") is not True:
        issues.append(
            _issue(
                "tshirt_fit_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest must declare T-shirt parameter fitting availability.",
            )
        )
    if caps.get("fittingQualityScored") is not True:
        issues.append(
            _issue(
                "fitting_quality_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest must declare fitting quality scoring availability.",
            )
        )
    for key, code in [
        ("imageConditionedFittingAvailable", "image_conditioned_fitting_capability_missing"),
        ("multiviewFittingLossAvailable", "multiview_fitting_loss_capability_missing"),
        ("confidenceWeightedFittingAvailable", "confidence_weighted_fitting_capability_missing"),
        ("fittingPriorsSeparatedAvailable", "fitting_priors_separated_capability_missing"),
        ("fittingOptimizationTraceAvailable", "fitting_optimization_trace_capability_missing"),
        ("fitAlternativesAvailable", "fit_alternatives_capability_missing"),
        (
            "heldOutPerturbationFitEvaluationAvailable",
            "held_out_perturbation_fit_capability_missing",
        ),
    ]:
        if caps.get(key) is not True:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "manifest.json",
                    f"Manifest capability {key} must be true for BP52 fitting.",
                )
            )
    if _contains_nonfinite(fit_report):
        issues.append(
            _issue(
                "tshirt_fit_nonfinite_numeric_value",
                "fatal",
                "fitting/tshirt_fit.json",
                "Fit report must not contain NaN or Infinity.",
            )
        )


def _validate_texture_identity(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    capture_record = _read_required_json(package_dir, "source/capture_record.json", issues)
    visual = _read_required_json(package_dir, "source/visual_observations.json", issues)
    fusion = _read_required_json(package_dir, "source/multiview_fusion.json", issues)
    fit_report = _read_required_json(package_dir, "fitting/tshirt_fit.json", issues)
    render_materials = _read_required_json(package_dir, "render/materials.json", issues)
    texture = _read_required_json(package_dir, "textures/texture_identity.json", issues)
    texture_quality = _read_required_json(package_dir, "reports/texture_quality.json", issues)
    if (
        capture_record is None
        or visual is None
        or fusion is None
        or fit_report is None
        or render_materials is None
        or texture is None
    ):
        return
    declared_capture_hash = _nested_string(capture_record, ["immutability", "sourceRecordHash"], "")
    declared_visual_hash = _nested_string(visual, ["integrity", "visualRecordHash"], "")
    declared_fusion_hash = _nested_string(fusion, ["integrity", "multiviewFusionRecordHash"], "")
    declared_fit_hash = _nested_string(fit_report, ["integrity", "fitReportHash"], "")
    if texture.get("sourceRecordId") != capture_record.get("recordId"):
        issues.append(
            _issue(
                "texture_identity_source_capture_mismatch",
                "fatal",
                "textures/texture_identity.json",
                "Texture identity must reference the capture record ID.",
            )
        )
    if texture.get("sourceRecordHash") != declared_capture_hash:
        issues.append(
            _issue(
                "texture_identity_source_hash_mismatch",
                "fatal",
                "textures/texture_identity.json",
                "Texture identity must reference the capture record hash.",
            )
        )
    if texture.get("sourceVisualUnderstandingId") != visual.get("visualUnderstandingId"):
        issues.append(
            _issue(
                "texture_identity_visual_mismatch",
                "fatal",
                "textures/texture_identity.json",
                "Texture identity must reference the visual observation ID.",
            )
        )
    if texture.get("sourceVisualRecordHash") != declared_visual_hash:
        issues.append(
            _issue(
                "texture_identity_visual_hash_mismatch",
                "fatal",
                "textures/texture_identity.json",
                "Texture identity must reference the visual observation hash.",
            )
        )
    if texture.get("sourceMultiviewFusionId") != fusion.get("fusionRecordId"):
        issues.append(
            _issue(
                "texture_identity_fusion_mismatch",
                "fatal",
                "textures/texture_identity.json",
                "BP53 texture identity must reference the multiview fusion ID.",
            )
        )
    if texture.get("sourceMultiviewFusionHash") != declared_fusion_hash:
        issues.append(
            _issue(
                "texture_identity_fusion_hash_mismatch",
                "fatal",
                "textures/texture_identity.json",
                "BP53 texture identity must reference the multiview fusion hash.",
            )
        )
    if texture.get("sourceFusedEvidenceHash") != _nested_string(
        fusion, ["fusedEvidence", "evidenceHash"], ""
    ):
        issues.append(
            _issue(
                "texture_identity_fused_evidence_hash_mismatch",
                "fatal",
                "textures/texture_identity.json",
                "BP53 texture identity must reference the fused visual evidence hash.",
            )
        )
    if texture.get("sourceCorrectedVisualRecordHash") != fusion.get(
        "sourceCorrectedVisualRecordHash"
    ):
        issues.append(
            _issue(
                "texture_identity_corrected_visual_hash_mismatch",
                "fatal",
                "textures/texture_identity.json",
                "BP53 texture identity must reference the corrected visual record hash.",
            )
        )
    if texture.get("sourceFitReportId") != fit_report.get("fitReportId"):
        issues.append(
            _issue(
                "texture_identity_fit_mismatch",
                "fatal",
                "textures/texture_identity.json",
                "Texture identity must reference the T-shirt fit report ID.",
            )
        )
    if texture.get("sourceFitReportHash") != declared_fit_hash:
        issues.append(
            _issue(
                "texture_identity_fit_hash_mismatch",
                "fatal",
                "textures/texture_identity.json",
                "Texture identity must reference the T-shirt fit report hash.",
            )
        )
    if _nested_string(texture, ["integrity", "textureIdentityHash"], "") != (
        hash_texture_identity_report(texture)
    ):
        issues.append(
            _issue(
                "texture_identity_hash_mismatch",
                "fatal",
                "textures/texture_identity.json",
                "Texture identity hash must match its canonical payload.",
            )
        )
    if texture.get("status") != "pass":
        issues.append(
            _issue(
                "texture_identity_not_pass",
                "fatal",
                "textures/texture_identity.json",
                "Texture identity report must pass for this canonical fixture.",
            )
        )
    texture_state = (
        texture.get("sourceTextureAvailable") is True
        and texture.get("generatedAtlasAvailable") is True
        and texture.get("textureProjectionRun") is True
    )
    if not texture_state:
        issues.append(
            _issue(
                "texture_identity_source_state_invalid",
                "fatal",
                "textures/texture_identity.json",
                "BP53 texture identity must run source projection and generate atlas metadata.",
            )
        )
    _validate_texture_projection_artifacts(package_dir, texture, issues)
    material_ids = {
        str(material.get("id"))
        for material in render_materials.get("materials", [])
        if isinstance(material, dict)
    }
    regions = texture.get("observedMaterialRegions", [])
    if not isinstance(regions, list) or not regions:
        issues.append(
            _issue(
                "texture_identity_material_regions_missing",
                "fatal",
                "textures/texture_identity.json",
                "Texture identity must include at least one observed material region.",
            )
        )
        regions = []
    for region in regions:
        if not isinstance(region, dict):
            issues.append(
                _issue(
                    "texture_identity_material_region_invalid",
                    "fatal",
                    "textures/texture_identity.json",
                    "Observed material regions must be objects.",
                )
            )
            continue
        material_id = str(region.get("materialId", ""))
        if material_id not in material_ids:
            issues.append(
                _issue(
                    "texture_identity_unknown_material",
                    "fatal",
                    "textures/texture_identity.json",
                    "Texture identity region references an unknown render material.",
                    material_id,
                )
            )
        _validate_texture_region_pbr(region, issues)
    plan = texture.get("projectionPlan", {})
    if not isinstance(plan, dict):
        issues.append(
            _issue(
                "texture_identity_projection_plan_invalid",
                "fatal",
                "textures/texture_identity.json",
                "Texture identity projectionPlan must be an object.",
            )
        )
    else:
        atlas_size = _int_or(plan.get("recommendedAtlasSizePx"), 0)
        if atlas_size <= 0 or atlas_size > 2048:
            issues.append(
                _issue(
                    "texture_identity_atlas_size_invalid",
                    "fatal",
                    "textures/texture_identity.json",
                    "Recommended atlas size must be mobile-safe.",
                )
            )
    if texture_quality is not None:
        if texture_quality.get("textureIdentityId") != texture.get("textureIdentityId"):
            issues.append(
                _issue(
                    "texture_quality_identity_mismatch",
                    "fatal",
                    "reports/texture_quality.json",
                    "Texture quality report must reference the texture identity ID.",
                )
            )
        if texture_quality.get("materialRegionCount") != len(regions):
            issues.append(
                _issue(
                    "texture_quality_region_count_mismatch",
                    "fatal",
                    "reports/texture_quality.json",
                    "Texture quality material region count must match texture identity.",
                )
            )
    caps = manifest.get("capabilities", {})
    if not isinstance(caps, dict):
        return
    if caps.get("textureIdentityEvidenceAvailable") is not True:
        issues.append(
            _issue(
                "texture_identity_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest must declare texture identity evidence availability.",
            )
        )
    if caps.get("pbrMaterialObservationAvailable") is not True:
        issues.append(
            _issue(
                "pbr_material_observation_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest must declare PBR material observation availability.",
            )
        )
    if caps.get("sourceImageTextureAvailable") is not True:
        issues.append(
            _issue(
                "texture_source_capability_contradiction",
                "fatal",
                "manifest.json",
                "sourceImageTextureAvailable must be true for BP53 source texture evidence.",
            )
        )
    for key, code in [
        ("sourceTextureProjectionAvailable", "source_texture_projection_capability_missing"),
        ("pbrMaterialMapExportAvailable", "pbr_map_export_capability_missing"),
        ("logoPrintPreservationMaskAvailable", "logo_print_mask_capability_missing"),
        (
            "controlledTextureInpaintingInterfaceAvailable",
            "controlled_inpainting_capability_missing",
        ),
    ]:
        if caps.get(key) is not True:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "manifest.json",
                    f"Manifest capability {key} must be true for BP53.",
                )
            )
    if _contains_nonfinite(texture):
        issues.append(
            _issue(
                "texture_identity_nonfinite_numeric_value",
                "fatal",
                "textures/texture_identity.json",
                "Texture identity report must not contain NaN or Infinity.",
            )
        )


def _validate_texture_region_pbr(region: dict[str, Any], issues: list[ValidationIssue]) -> None:
    pbr = region.get("pbr", {})
    if not isinstance(pbr, dict):
        issues.append(
            _issue(
                "texture_identity_pbr_invalid",
                "fatal",
                "textures/texture_identity.json",
                "Texture identity material region must include a PBR object.",
            )
        )
        return
    base_color = pbr.get("baseColorFactor")
    if not isinstance(base_color, list | tuple) or len(base_color) != 4:
        issues.append(
            _issue(
                "texture_identity_pbr_color_invalid",
                "fatal",
                "textures/texture_identity.json",
                "PBR baseColorFactor must contain four channel values.",
            )
        )
    else:
        for channel in base_color:
            channel_value = _float_or(channel, math.nan)
            if not math.isfinite(channel_value) or not 0.0 <= channel_value <= 1.0:
                issues.append(
                    _issue(
                        "texture_identity_pbr_color_invalid",
                        "fatal",
                        "textures/texture_identity.json",
                        "PBR baseColorFactor channels must be inside [0, 1].",
                    )
                )
                break
    for key in ("roughnessFactor", "metallicFactor"):
        value = _float_or(pbr.get(key), math.nan)
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            issues.append(
                _issue(
                    "texture_identity_pbr_factor_invalid",
                    "fatal",
                    "textures/texture_identity.json",
                    f"PBR {key} must be finite and inside [0, 1].",
                    str(region.get("regionId", "")),
                )
            )


def _validate_texture_projection_artifacts(
    package_dir: Path, texture: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    expected_paths = {
        "sourceProjection": "textures/source_projection.json",
        "generatedAtlas": "textures/generated_atlas.json",
        "pbrMaterialMaps": "textures/pbr_material_maps.json",
        "conventionalFallbackMaterials": "textures/conventional_fallback_materials.json",
    }
    artifact_refs = texture.get("artifactRefs")
    if not isinstance(artifact_refs, dict):
        issues.append(
            _issue(
                "texture_artifact_refs_missing",
                "fatal",
                "textures/texture_identity.json",
                "BP53 texture identity must include artifactRefs.",
            )
        )
        return

    artifacts: dict[str, dict[str, Any]] = {}
    for key, relpath in expected_paths.items():
        ref = artifact_refs.get(key)
        if not isinstance(ref, dict):
            issues.append(
                _issue(
                    "texture_artifact_ref_missing",
                    "fatal",
                    "textures/texture_identity.json",
                    f"BP53 texture artifact ref {key} is required.",
                )
            )
            continue
        if ref.get("path") != relpath:
            issues.append(
                _issue(
                    "texture_artifact_ref_path_invalid",
                    "fatal",
                    "textures/texture_identity.json",
                    f"BP53 texture artifact ref {key} must point to {relpath}.",
                )
            )
            continue
        artifact = _read_required_json(package_dir, relpath, issues)
        if artifact is None:
            continue
        artifacts[key] = artifact
        declared_file_hash = str(ref.get("sha256", ""))
        actual_file_hash = _json_hash(artifact)
        if declared_file_hash != actual_file_hash:
            issues.append(
                _issue(
                    "texture_artifact_ref_hash_mismatch",
                    "fatal",
                    "textures/texture_identity.json",
                    "Texture artifact ref hash must match the canonical artifact payload.",
                    relpath,
                )
            )
        declared_internal_hash = _nested_string(artifact, ["integrity", "artifactHash"], "")
        if declared_internal_hash != _json_hash_with_blank(artifact, "artifactHash"):
            issues.append(
                _issue(
                    "texture_artifact_internal_hash_mismatch",
                    "fatal",
                    relpath,
                    "Texture artifact internal hash must match the canonical payload.",
                )
            )

    source_projection = artifacts.get("sourceProjection", {})
    projections = source_projection.get("projections", [])
    if not isinstance(projections, list) or not projections:
        issues.append(
            _issue(
                "texture_source_projection_missing",
                "fatal",
                "textures/source_projection.json",
                "BP53 source projection artifact must include projection records.",
            )
        )
        projections = []
    visible_count = sum(
        1
        for projection in projections
        if isinstance(projection, dict) and projection.get("visibleSourceEvidence") is True
    )
    if visible_count <= 0:
        issues.append(
            _issue(
                "texture_source_projection_visible_evidence_missing",
                "fatal",
                "textures/source_projection.json",
                "BP53 source projection must include at least one visible source-backed region.",
            )
        )
    if _nested_string(source_projection, ["policy", "rawPixelsExported"], "true") != "":
        policy = source_projection.get("policy", {})
        if not isinstance(policy, dict) or policy.get("rawPixelsExported") is not False:
            issues.append(
                _issue(
                    "texture_source_projection_exports_raw_pixels",
                    "fatal",
                    "textures/source_projection.json",
                    "Texture projection artifacts must not export raw source pixels.",
                )
            )
    for projection in projections:
        if not isinstance(projection, dict):
            continue
        for point in projection.get("sourceProjectionCoordinates", []):
            _validate_normalised_point(point, "texture_projection_point_out_of_range", issues)
        for point in projection.get("targetProjectionCoordinates", []):
            _validate_normalised_point(point, "texture_projection_point_out_of_range", issues)

    controlled = texture.get("controlledInpainting", {})
    if (
        not isinstance(controlled, dict)
        or controlled.get("visibleEvidenceOverwriteAllowed") is not False
    ):
        issues.append(
            _issue(
                "texture_inpainting_overwrite_policy_invalid",
                "fatal",
                "textures/texture_identity.json",
                "Controlled texture inpainting must forbid visible source evidence overwrite.",
            )
        )
    for operation in (
        controlled.get("allowedOperations", []) if isinstance(controlled, dict) else []
    ):
        if (
            isinstance(operation, dict)
            and operation.get("overwriteVisibleSourceEvidence") is not False
        ):
            issues.append(
                _issue(
                    "texture_inpainting_visible_overwrite_allowed",
                    "fatal",
                    "textures/texture_identity.json",
                    "Allowed inpainting operations must never overwrite visible source evidence.",
                )
            )
    if _int_or(controlled.get("overwriteVisibleSourceEvidenceRejectedCount"), 0) <= 0:
        issues.append(
            _issue(
                "texture_inpainting_rejection_evidence_missing",
                "fatal",
                "textures/texture_identity.json",
                "Controlled texture inpainting must include visible-overwrite rejection evidence.",
            )
        )

    atlas = artifacts.get("generatedAtlas", {})
    if atlas.get("rawSourcePixelsEmbedded") is not False:
        issues.append(
            _issue(
                "texture_atlas_raw_pixels_embedded",
                "fatal",
                "textures/generated_atlas.json",
                "Generated atlas artifact must remain a portable summary, not raw pixels.",
            )
        )
    pbr_maps = artifacts.get("pbrMaterialMaps", {})
    if _int_or(pbr_maps.get("materialMapCount"), 0) <= 0:
        issues.append(
            _issue(
                "texture_pbr_maps_missing",
                "fatal",
                "textures/pbr_material_maps.json",
                "BP53 PBR material-map artifact must contain material map records.",
            )
        )
    if _int_or(_mapping(pbr_maps.get("aggregate")).get("advancedShaderFeatureCount"), 1) != 0:
        issues.append(
            _issue(
                "texture_pbr_advanced_shader_feature_invalid",
                "fatal",
                "textures/pbr_material_maps.json",
                "BP53 PBR maps must remain mobile-safe and avoid advanced shader features.",
            )
        )


def _validate_geometry_proposal(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    capture_record = _read_required_json(package_dir, "source/capture_record.json", issues)
    visual = _read_required_json(package_dir, "source/visual_observations.json", issues)
    fit_report = _read_required_json(package_dir, "fitting/tshirt_fit.json", issues)
    texture = _read_required_json(package_dir, "textures/texture_identity.json", issues)
    proposal = _read_required_json(package_dir, "proposals/raw_geometry_proposal.json", issues)
    proposal_quality = _read_required_json(
        package_dir, "reports/geometry_proposal_quality.json", issues
    )
    if (
        capture_record is None
        or visual is None
        or fit_report is None
        or texture is None
        or proposal is None
    ):
        return
    if proposal.get("garmentId") != manifest.get("garmentId"):
        issues.append(
            _issue(
                "geometry_proposal_garment_mismatch",
                "fatal",
                "proposals/raw_geometry_proposal.json",
                "Geometry proposal must reference the package garment ID.",
            )
        )
    if proposal.get("garmentClass") != manifest.get("garmentClass"):
        issues.append(
            _issue(
                "geometry_proposal_class_mismatch",
                "fatal",
                "proposals/raw_geometry_proposal.json",
                "Geometry proposal must reference the package garment class.",
            )
        )
    expected_hashes = [
        (
            "sourceRecordHash",
            _nested_string(capture_record, ["immutability", "sourceRecordHash"], ""),
            "geometry_proposal_source_hash_mismatch",
        ),
        (
            "sourceVisualRecordHash",
            _nested_string(visual, ["integrity", "visualRecordHash"], ""),
            "geometry_proposal_visual_hash_mismatch",
        ),
        (
            "sourceFitReportHash",
            _nested_string(fit_report, ["integrity", "fitReportHash"], ""),
            "geometry_proposal_fit_hash_mismatch",
        ),
        (
            "sourceTextureIdentityHash",
            _nested_string(texture, ["integrity", "textureIdentityHash"], ""),
            "geometry_proposal_texture_hash_mismatch",
        ),
    ]
    for field, expected_hash, code in expected_hashes:
        if proposal.get(field) != expected_hash:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "proposals/raw_geometry_proposal.json",
                    f"Geometry proposal {field} must match its source artifact.",
                )
            )
    if _nested_string(proposal, ["integrity", "geometryProposalHash"], "") != (
        hash_geometry_proposal(proposal)
    ):
        issues.append(
            _issue(
                "geometry_proposal_hash_mismatch",
                "fatal",
                "proposals/raw_geometry_proposal.json",
                "Geometry proposal hash must match its canonical payload.",
            )
        )
    provider = proposal.get("provider", {})
    policy = proposal.get("policy", {})
    request = proposal.get("request", {})
    raw = proposal.get("rawProposal", {})
    clean = proposal.get("cleanProposal", {})
    quality = proposal.get("quality", {})
    audit = proposal.get("geometryAudit", {})
    for name, block in [
        ("provider", provider),
        ("policy", policy),
        ("request", request),
        ("rawProposal", raw),
        ("cleanProposal", clean),
        ("quality", quality),
        ("geometryAudit", audit),
    ]:
        if not isinstance(block, dict):
            issues.append(
                _issue(
                    "geometry_proposal_block_invalid",
                    "fatal",
                    "proposals/raw_geometry_proposal.json",
                    f"Geometry proposal {name} block must be an object.",
                )
            )
            return
    if (
        provider.get("runtimeExternalApis") is not False
        or provider.get("allowTrainingUse") is not False
        or provider.get("containsUserImagery") is not False
        or policy.get("allowExternalApis") is not False
        or policy.get("allowTrainingUse") is not False
        or policy.get("containsUserImagery") is not False
        or policy.get("containsPersonalBodyData") is not False
    ):
        issues.append(
            _issue(
                "geometry_proposal_provider_policy_violation",
                "fatal",
                "proposals/raw_geometry_proposal.json",
                "Null/manual proposal fixture cannot use external APIs, training use or user data.",
            )
        )
    if (
        request.get("purpose") != "garment_visual_geometry_proposal"
        or request.get("supportedDomain") != "avatar_garment_only"
    ):
        issues.append(
            _issue(
                "geometry_proposal_domain_invalid",
                "fatal",
                "proposals/raw_geometry_proposal.json",
                "Geometry proposal requests must be constrained to avatar/garment use.",
            )
        )
    if policy.get("approvedDomain") != "avatar_and_garment_only":
        issues.append(
            _issue(
                "geometry_proposal_domain_invalid",
                "fatal",
                "proposals/raw_geometry_proposal.json",
                "Geometry proposal policy must approve only avatar-and-garment scope.",
            )
        )
    if raw.get("noCanonicalUse") is not True:
        issues.append(
            _issue(
                "geometry_proposal_raw_canonical_use_invalid",
                "fatal",
                "proposals/raw_geometry_proposal.json",
                "Raw geometry proposals must explicitly forbid canonical use.",
            )
        )
    if quality.get("acceptedForCanonical") is not False:
        issues.append(
            _issue(
                "geometry_proposal_canonical_acceptance_invalid",
                "fatal",
                "proposals/raw_geometry_proposal.json",
                "Null/manual raw proposals cannot be accepted as canonical garment truth.",
            )
        )
    provider_id = str(provider.get("providerId", ""))
    if provider_id == "closy.null_geometry_proposal_provider.v1":
        _validate_null_geometry_proposal_payload(raw, clean, quality, audit, issues)
    elif provider_id == "closy.manual_local_glb_import.v1":
        _validate_manual_geometry_proposal_payload(package_dir, raw, clean, quality, audit, issues)
    else:
        issues.append(
            _issue(
                "geometry_proposal_provider_invalid",
                "fatal",
                "proposals/raw_geometry_proposal.json",
                "Unknown geometry proposal provider for v1 package validation.",
            )
        )
    if proposal_quality is not None:
        if proposal_quality.get("proposalId") != proposal.get("proposalId"):
            issues.append(
                _issue(
                    "geometry_proposal_quality_mismatch",
                    "fatal",
                    "reports/geometry_proposal_quality.json",
                    "Geometry proposal quality report must reference the proposal ID.",
                )
            )
        if proposal_quality.get("acceptedForCanonical") != quality.get("acceptedForCanonical"):
            issues.append(
                _issue(
                    "geometry_proposal_quality_mismatch",
                    "fatal",
                    "reports/geometry_proposal_quality.json",
                    "Geometry proposal quality acceptance must match the proposal.",
                )
            )
    caps = manifest.get("capabilities", {})
    if not isinstance(caps, dict):
        return
    expected_capabilities = [
        ("geometryProposalInterfaceAvailable", True, "geometry_proposal_capability_missing"),
        ("rawGeometryProposalRecordAvailable", True, "geometry_proposal_capability_missing"),
        ("geometryProposalQualityScored", True, "geometry_proposal_capability_missing"),
        (
            "rawGeometryTopologyDiagnosticsAvailable",
            True,
            "raw_geometry_topology_capability_missing",
        ),
        (
            "geometryCleanupRecommendationAvailable",
            True,
            "geometry_cleanup_recommendation_capability_missing",
        ),
        (
            "geometryCleanupExecutionAvailable",
            True,
            "geometry_cleanup_execution_capability_missing",
        ),
        (
            "geometrySemanticTransferAvailable",
            True,
            "geometry_semantic_transfer_capability_missing",
        ),
        (
            "geometryBoundaryClassificationAvailable",
            True,
            "geometry_boundary_classification_capability_missing",
        ),
        (
            "geometryBindingCandidateAvailable",
            True,
            "geometry_binding_candidate_capability_missing",
        ),
        (
            "geometryBindingValidationAvailable",
            True,
            "geometry_binding_validation_capability_missing",
        ),
        (
            "geometryRepairRetopologyPlanAvailable",
            True,
            "geometry_repair_retopology_plan_capability_missing",
        ),
        (
            "geometryRepairResultAvailable",
            True,
            "geometry_repair_result_capability_missing",
        ),
        (
            "geometryRuntimeBindingResultAvailable",
            True,
            "geometry_runtime_binding_result_capability_missing",
        ),
        (
            "geometryCleanAcceptanceGateAvailable",
            True,
            "geometry_clean_acceptance_gate_capability_missing",
        ),
        ("providerProvenanceAvailable", True, "provider_provenance_capability_missing"),
        ("cleanGeometryProposalAvailable", False, "clean_geometry_proposal_capability_invalid"),
    ]
    for key, expected, code in expected_capabilities:
        if caps.get(key) is not expected:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "manifest.json",
                    f"Manifest capability {key} must be {expected!r} for the null provider.",
                )
            )
    if _contains_nonfinite(proposal):
        issues.append(
            _issue(
                "geometry_proposal_nonfinite_numeric_value",
                "fatal",
                "proposals/raw_geometry_proposal.json",
                "Geometry proposal report must not contain NaN or Infinity.",
            )
        )


def _validate_null_geometry_proposal_payload(
    raw: dict[str, Any],
    clean: dict[str, Any],
    quality: dict[str, Any],
    audit: dict[str, Any],
    issues: list[ValidationIssue],
) -> None:
    if quality.get("status") != "rejected":
        issues.append(
            _issue(
                "geometry_proposal_status_invalid",
                "fatal",
                "proposals/raw_geometry_proposal.json",
                "The deterministic null provider proposal must be rejected.",
            )
        )
    if raw.get("available") is not False or clean.get("available") is not False:
        issues.append(
            _issue(
                "geometry_proposal_availability_invalid",
                "fatal",
                "proposals/raw_geometry_proposal.json",
                "Null provider must not claim raw or clean geometry availability.",
            )
        )
    if _int_or(audit.get("meshCount"), -1) != 0 or _int_or(audit.get("triangleEstimate"), -1) != 0:
        issues.append(
            _issue(
                "geometry_proposal_audit_invalid",
                "fatal",
                "proposals/raw_geometry_proposal.json",
                "Null provider geometry audit must report zero meshes and triangles.",
            )
        )


def _validate_manual_geometry_proposal_payload(
    package_dir: Path,
    raw: dict[str, Any],
    clean: dict[str, Any],
    quality: dict[str, Any],
    audit: dict[str, Any],
    issues: list[ValidationIssue],
) -> None:
    if quality.get("status") != "accepted_visual_reference":
        issues.append(
            _issue(
                "geometry_proposal_status_invalid",
                "fatal",
                "proposals/raw_geometry_proposal.json",
                "Manual local GLB proposals must be accepted only as visual reference.",
            )
        )
    if raw.get("available") is not True or clean.get("available") is not False:
        issues.append(
            _issue(
                "geometry_proposal_availability_invalid",
                "fatal",
                "proposals/raw_geometry_proposal.json",
                "Manual local proposal must have raw geometry and no clean proposal.",
            )
        )
    if quality.get("acceptedForVisualReference") is not True:
        issues.append(
            _issue(
                "geometry_proposal_visual_reference_invalid",
                "fatal",
                "proposals/raw_geometry_proposal.json",
                "Manual local proposal must explicitly be visual-reference only.",
            )
        )
    raw_asset = raw.get("assetPath")
    if not isinstance(raw_asset, str):
        issues.append(
            _issue(
                "geometry_proposal_asset_path_invalid",
                "fatal",
                "proposals/raw_geometry_proposal.json",
                "Manual raw proposal must provide a package-relative GLB path.",
            )
        )
        return
    try:
        validate_package_relpath(raw_asset)
    except ValueError:
        issues.append(
            _issue(
                "geometry_proposal_asset_path_invalid",
                "fatal",
                "proposals/raw_geometry_proposal.json",
                "Manual raw proposal asset path is unsafe.",
            )
        )
        return
    asset_path = package_dir / raw_asset
    if not asset_path.exists():
        issues.append(
            _issue(
                "geometry_proposal_asset_missing",
                "fatal",
                raw_asset,
                "Manual raw proposal GLB is missing.",
            )
        )
        return
    try:
        glb_audit = audit_glb(asset_path)
    except Exception as exc:
        issues.append(_issue("geometry_proposal_asset_audit_failed", "fatal", raw_asset, str(exc)))
        return
    if raw.get("sourceAssetHash") != sha256_file(asset_path):
        issues.append(
            _issue(
                "geometry_proposal_asset_hash_mismatch",
                "fatal",
                "proposals/raw_geometry_proposal.json",
                "Manual raw proposal asset hash is stale.",
            )
        )
    if raw.get("byteSize") != asset_path.stat().st_size:
        issues.append(
            _issue(
                "geometry_proposal_asset_size_mismatch",
                "fatal",
                "proposals/raw_geometry_proposal.json",
                "Manual raw proposal asset byte size is stale.",
            )
        )
    expected_counts = {
        "meshCount": glb_audit["meshCount"],
        "visibleMeshCount": glb_audit["primitiveCount"],
        "triangleEstimate": glb_audit["triangleEstimate"],
        "materialCount": glb_audit["materialCount"],
    }
    for key, expected in expected_counts.items():
        if _int_or(audit.get(key), -1) != int(expected):
            issues.append(
                _issue(
                    "geometry_proposal_audit_mismatch",
                    "fatal",
                    "proposals/raw_geometry_proposal.json",
                    f"Manual raw proposal audit field {key} is stale.",
                )
            )
    if (
        _int_or(audit.get("meshCount"), 0) <= 0
        or _int_or(audit.get("visibleMeshCount"), 0) <= 0
        or _int_or(audit.get("triangleEstimate"), 0) <= 0
    ):
        issues.append(
            _issue(
                "geometry_proposal_audit_invalid",
                "fatal",
                "proposals/raw_geometry_proposal.json",
                "Manual raw proposal GLB must contain visible renderable triangles.",
            )
        )


def _validate_raw_geometry_topology(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    proposal = _read_required_json(package_dir, "proposals/raw_geometry_proposal.json", issues)
    topology = _read_required_json(package_dir, "reports/raw_geometry_topology.json", issues)
    if proposal is None or topology is None:
        return

    if topology.get("garmentId") != manifest.get("garmentId"):
        issues.append(
            _issue(
                "raw_geometry_topology_garment_mismatch",
                "fatal",
                "reports/raw_geometry_topology.json",
                "Raw topology report must reference the package garment ID.",
            )
        )
    if topology.get("garmentClass") != manifest.get("garmentClass"):
        issues.append(
            _issue(
                "raw_geometry_topology_class_mismatch",
                "fatal",
                "reports/raw_geometry_topology.json",
                "Raw topology report must reference the package garment class.",
            )
        )
    if topology.get("sourceRawProposalId") != proposal.get("proposalId"):
        issues.append(
            _issue(
                "raw_geometry_topology_source_mismatch",
                "fatal",
                "reports/raw_geometry_topology.json",
                "Raw topology report must reference the raw proposal ID.",
            )
        )
    if topology.get("sourceRawProposalHash") != _nested_string(
        proposal, ["integrity", "geometryProposalHash"], ""
    ):
        issues.append(
            _issue(
                "raw_geometry_topology_source_hash_mismatch",
                "fatal",
                "reports/raw_geometry_topology.json",
                "Raw topology report must reference the raw proposal hash.",
            )
        )

    raw = proposal.get("rawProposal", {})
    if not isinstance(raw, dict) or raw.get("available") is not True:
        issues.append(
            _issue(
                "raw_geometry_topology_source_unavailable",
                "fatal",
                "reports/raw_geometry_topology.json",
                "Raw topology diagnostics require an available raw GLB proposal.",
            )
        )
        return
    raw_asset = raw.get("assetPath")
    if not isinstance(raw_asset, str):
        issues.append(
            _issue(
                "raw_geometry_topology_asset_path_invalid",
                "fatal",
                "reports/raw_geometry_topology.json",
                "Raw topology diagnostics require a package-relative GLB path.",
            )
        )
        return
    try:
        validate_package_relpath(raw_asset)
    except ValueError:
        issues.append(
            _issue(
                "raw_geometry_topology_asset_path_invalid",
                "fatal",
                "reports/raw_geometry_topology.json",
                "Raw topology diagnostics asset path is unsafe.",
            )
        )
        return
    asset_path = package_dir / raw_asset
    if not asset_path.exists():
        issues.append(
            _issue(
                "raw_geometry_topology_asset_missing",
                "fatal",
                raw_asset,
                "Raw topology diagnostics asset is missing.",
            )
        )
        return

    if topology.get("sourceRawAssetPath") != raw_asset:
        issues.append(
            _issue(
                "raw_geometry_topology_asset_mismatch",
                "fatal",
                "reports/raw_geometry_topology.json",
                "Raw topology asset path must mirror the raw proposal.",
            )
        )
    if topology.get("sourceRawAssetHash") != raw.get("sourceAssetHash"):
        issues.append(
            _issue(
                "raw_geometry_topology_asset_hash_mismatch",
                "fatal",
                "reports/raw_geometry_topology.json",
                "Raw topology asset hash must mirror the raw proposal.",
            )
        )
    if topology.get("sourceRawAssetByteSize") != raw.get("byteSize"):
        issues.append(
            _issue(
                "raw_geometry_topology_asset_size_mismatch",
                "fatal",
                "reports/raw_geometry_topology.json",
                "Raw topology asset size must mirror the raw proposal.",
            )
        )
    if _nested_string(topology, ["integrity", "rawGeometryTopologyReportHash"], "") != (
        hash_raw_geometry_topology_report(topology)
    ):
        issues.append(
            _issue(
                "raw_geometry_topology_hash_mismatch",
                "fatal",
                "reports/raw_geometry_topology.json",
                "Raw topology report hash must match its canonical payload.",
            )
        )

    try:
        expected = build_raw_geometry_topology_report(
            garment_id=str(manifest.get("garmentId", "")),
            garment_class=str(manifest.get("garmentClass", "")),
            raw_geometry_proposal=proposal,
            asset_path=asset_path,
        )
    except Exception as exc:
        issues.append(
            _issue(
                "raw_geometry_topology_recompute_failed",
                "fatal",
                "reports/raw_geometry_topology.json",
                str(exc),
            )
        )
        return

    expected_fields = [
        ("inputAudit", "meshCount"),
        ("inputAudit", "visibleMeshCount"),
        ("inputAudit", "triangleEstimate"),
        ("inputAudit", "materialCount"),
        ("topology", "meshCount"),
        ("topology", "vertexCount"),
        ("topology", "triangleCount"),
        ("topology", "componentCount"),
        ("topology", "largestComponentTriangleCount"),
        ("topology", "boundaryEdgeCount"),
        ("topology", "nonManifoldEdgeCount"),
        ("topology", "degenerateTriangleCount"),
        ("topology", "duplicatePositionCount"),
        ("topology", "manifoldStatus"),
    ]
    for block_name, key in expected_fields:
        block = topology.get(block_name, {})
        expected_block = expected.get(block_name, {})
        if not isinstance(block, dict) or not isinstance(expected_block, dict):
            continue
        if block.get(key) != expected_block.get(key):
            issues.append(
                _issue(
                    "raw_geometry_topology_diagnostics_mismatch",
                    "fatal",
                    "reports/raw_geometry_topology.json",
                    f"Raw topology diagnostics field {block_name}.{key} is stale.",
                )
            )

    readiness = topology.get("cleanReadiness", {})
    policy = topology.get("policy", {})
    if not isinstance(readiness, dict) or not isinstance(policy, dict):
        issues.append(
            _issue(
                "raw_geometry_topology_block_invalid",
                "fatal",
                "reports/raw_geometry_topology.json",
                "Raw topology report readiness and policy blocks must be objects.",
            )
        )
        return
    if readiness.get("acceptedForCleanProposal") is not False:
        issues.append(
            _issue(
                "raw_geometry_topology_clean_acceptance_invalid",
                "fatal",
                "reports/raw_geometry_topology.json",
                "Raw topology diagnostics alone cannot accept a clean proposal.",
            )
        )
    if (
        policy.get("allowExternalApis") is not False
        or policy.get("allowTrainingUse") is not False
        or policy.get("containsUserImagery") is not False
        or policy.get("containsPersonalBodyData") is not False
        or policy.get("approvedDomain") != "avatar_and_garment_only"
    ):
        issues.append(
            _issue(
                "raw_geometry_topology_policy_violation",
                "fatal",
                "reports/raw_geometry_topology.json",
                "Raw topology diagnostics cannot permit external APIs, training use or user data.",
            )
        )
    caps = manifest.get("capabilities", {})
    if isinstance(caps, dict) and caps.get("rawGeometryTopologyDiagnosticsAvailable") is not True:
        issues.append(
            _issue(
                "raw_geometry_topology_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest must declare raw geometry topology diagnostics availability.",
            )
        )
    if _contains_nonfinite(topology):
        issues.append(
            _issue(
                "raw_geometry_topology_nonfinite_numeric_value",
                "fatal",
                "reports/raw_geometry_topology.json",
                "Raw topology report must not contain NaN or Infinity.",
            )
        )


def _validate_geometry_cleanup_plan(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    proposal = _read_required_json(package_dir, "proposals/raw_geometry_proposal.json", issues)
    raw_topology = _read_required_json(package_dir, "reports/raw_geometry_topology.json", issues)
    cleanup_plan = _read_required_json(package_dir, "reports/geometry_cleanup_plan.json", issues)
    if proposal is None or raw_topology is None or cleanup_plan is None:
        return

    if cleanup_plan.get("garmentId") != manifest.get("garmentId"):
        issues.append(
            _issue(
                "geometry_cleanup_plan_garment_mismatch",
                "fatal",
                "reports/geometry_cleanup_plan.json",
                "Cleanup plan must reference the package garment ID.",
            )
        )
    if cleanup_plan.get("garmentClass") != manifest.get("garmentClass"):
        issues.append(
            _issue(
                "geometry_cleanup_plan_class_mismatch",
                "fatal",
                "reports/geometry_cleanup_plan.json",
                "Cleanup plan must reference the package garment class.",
            )
        )
    if cleanup_plan.get("sourceRawProposalId") != proposal.get("proposalId"):
        issues.append(
            _issue(
                "geometry_cleanup_plan_raw_source_mismatch",
                "fatal",
                "reports/geometry_cleanup_plan.json",
                "Cleanup plan must reference the raw proposal ID.",
            )
        )
    if cleanup_plan.get("sourceRawTopologyReportId") != raw_topology.get("reportId"):
        issues.append(
            _issue(
                "geometry_cleanup_plan_topology_source_mismatch",
                "fatal",
                "reports/geometry_cleanup_plan.json",
                "Cleanup plan must reference the raw topology report ID.",
            )
        )
    expected_hashes = [
        (
            "sourceRawProposalHash",
            _nested_string(proposal, ["integrity", "geometryProposalHash"], ""),
            "geometry_cleanup_plan_raw_hash_mismatch",
        ),
        (
            "sourceRawTopologyReportHash",
            _nested_string(raw_topology, ["integrity", "rawGeometryTopologyReportHash"], ""),
            "geometry_cleanup_plan_topology_hash_mismatch",
        ),
    ]
    for field, expected_hash, code in expected_hashes:
        if cleanup_plan.get(field) != expected_hash:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "reports/geometry_cleanup_plan.json",
                    f"Cleanup plan {field} must match its source artifact.",
                )
            )
    if _nested_string(cleanup_plan, ["integrity", "geometryCleanupPlanHash"], "") != (
        hash_geometry_cleanup_plan(cleanup_plan)
    ):
        issues.append(
            _issue(
                "geometry_cleanup_plan_hash_mismatch",
                "fatal",
                "reports/geometry_cleanup_plan.json",
                "Cleanup plan hash must match its canonical payload.",
            )
        )

    try:
        expected = build_geometry_cleanup_plan(
            garment_id=str(manifest.get("garmentId", "")),
            garment_class=str(manifest.get("garmentClass", "")),
            raw_geometry_proposal=proposal,
            raw_topology_report=raw_topology,
        )
    except Exception as exc:
        issues.append(
            _issue(
                "geometry_cleanup_plan_recompute_failed",
                "fatal",
                "reports/geometry_cleanup_plan.json",
                str(exc),
            )
        )
        return

    snapshot = cleanup_plan.get("topologySnapshot", {})
    expected_snapshot = expected.get("topologySnapshot", {})
    if isinstance(snapshot, dict) and isinstance(expected_snapshot, dict):
        for key, expected_value in expected_snapshot.items():
            if snapshot.get(key) != expected_value:
                issues.append(
                    _issue(
                        "geometry_cleanup_plan_topology_snapshot_mismatch",
                        "fatal",
                        "reports/geometry_cleanup_plan.json",
                        f"Cleanup plan topology snapshot field {key} is stale.",
                    )
                )

    operations = cleanup_plan.get("recommendedOperations", [])
    expected_operations = expected.get("recommendedOperations", [])
    if not isinstance(operations, list) or operations != expected_operations:
        issues.append(
            _issue(
                "geometry_cleanup_plan_operations_mismatch",
                "fatal",
                "reports/geometry_cleanup_plan.json",
                "Cleanup plan recommended operations must match topology diagnostics.",
            )
        )

    execution = cleanup_plan.get("execution", {})
    readiness = cleanup_plan.get("readiness", {})
    policy = cleanup_plan.get("policy", {})
    for name, block in [
        ("execution", execution),
        ("readiness", readiness),
        ("policy", policy),
    ]:
        if not isinstance(block, dict):
            issues.append(
                _issue(
                    "geometry_cleanup_plan_block_invalid",
                    "fatal",
                    "reports/geometry_cleanup_plan.json",
                    f"Cleanup plan {name} block must be an object.",
                )
            )
            return
    if (
        execution.get("cleanupRun") is not False
        or execution.get("repairRun") is not False
        or execution.get("retopologyRun") is not False
        or execution.get("semanticTransferRun") is not False
        or execution.get("simulationBindingRun") is not False
        or execution.get("outputAssetPath") is not None
        or execution.get("outputAssetHash") is not None
    ):
        issues.append(
            _issue(
                "geometry_cleanup_plan_execution_state_invalid",
                "fatal",
                "reports/geometry_cleanup_plan.json",
                "Cleanup recommendation plans must not claim executed repair output.",
            )
        )
    if (
        readiness.get("status") != "blocked_not_executed"
        or readiness.get("acceptedForCleanProposal") is not False
        or readiness.get("acceptedForCanonical") is not False
        or readiness.get("acceptedForSimulation") is not False
        or readiness.get("acceptedForRuntimeRender") is not False
    ):
        issues.append(
            _issue(
                "geometry_cleanup_plan_clean_acceptance_invalid",
                "fatal",
                "reports/geometry_cleanup_plan.json",
                "Cleanup recommendation plans cannot accept clean/canonical/runtime geometry.",
            )
        )
    if (
        policy.get("allowExternalApis") is not False
        or policy.get("allowTrainingUse") is not False
        or policy.get("containsUserImagery") is not False
        or policy.get("containsPersonalBodyData") is not False
        or policy.get("approvedDomain") != "avatar_and_garment_only"
    ):
        issues.append(
            _issue(
                "geometry_cleanup_plan_policy_violation",
                "fatal",
                "reports/geometry_cleanup_plan.json",
                "Cleanup plans cannot permit external APIs, training use or user data.",
            )
        )
    caps = manifest.get("capabilities", {})
    if isinstance(caps, dict) and caps.get("geometryCleanupRecommendationAvailable") is not True:
        issues.append(
            _issue(
                "geometry_cleanup_recommendation_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest must declare cleanup recommendation availability.",
            )
        )
    if _contains_nonfinite(cleanup_plan):
        issues.append(
            _issue(
                "geometry_cleanup_plan_nonfinite_numeric_value",
                "fatal",
                "reports/geometry_cleanup_plan.json",
                "Cleanup plan report must not contain NaN or Infinity.",
            )
        )


def _validate_geometry_cleanup_result(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    proposal = _read_required_json(package_dir, "proposals/raw_geometry_proposal.json", issues)
    raw_topology = _read_required_json(package_dir, "reports/raw_geometry_topology.json", issues)
    cleanup_plan = _read_required_json(package_dir, "reports/geometry_cleanup_plan.json", issues)
    cleanup_result = _read_required_json(
        package_dir, "reports/geometry_cleanup_result.json", issues
    )
    if proposal is None or raw_topology is None or cleanup_plan is None or cleanup_result is None:
        return

    if cleanup_result.get("garmentId") != manifest.get("garmentId"):
        issues.append(
            _issue(
                "geometry_cleanup_result_garment_mismatch",
                "fatal",
                "reports/geometry_cleanup_result.json",
                "Cleanup result must reference the package garment ID.",
            )
        )
    if cleanup_result.get("garmentClass") != manifest.get("garmentClass"):
        issues.append(
            _issue(
                "geometry_cleanup_result_class_mismatch",
                "fatal",
                "reports/geometry_cleanup_result.json",
                "Cleanup result must reference the package garment class.",
            )
        )
    expected_hashes = [
        (
            "sourceRawProposalHash",
            _nested_string(proposal, ["integrity", "geometryProposalHash"], ""),
            "geometry_cleanup_result_raw_hash_mismatch",
        ),
        (
            "sourceRawTopologyReportHash",
            _nested_string(raw_topology, ["integrity", "rawGeometryTopologyReportHash"], ""),
            "geometry_cleanup_result_topology_hash_mismatch",
        ),
        (
            "sourceGeometryCleanupPlanHash",
            _nested_string(cleanup_plan, ["integrity", "geometryCleanupPlanHash"], ""),
            "geometry_cleanup_result_plan_hash_mismatch",
        ),
    ]
    for field, expected_hash, code in expected_hashes:
        if cleanup_result.get(field) != expected_hash:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "reports/geometry_cleanup_result.json",
                    f"Cleanup result {field} must match its source artifact.",
                )
            )
    expected_ids = [
        (
            "sourceRawProposalId",
            proposal.get("proposalId"),
            "geometry_cleanup_result_raw_source_mismatch",
        ),
        (
            "sourceRawTopologyReportId",
            raw_topology.get("reportId"),
            "geometry_cleanup_result_topology_source_mismatch",
        ),
        (
            "sourceGeometryCleanupPlanId",
            cleanup_plan.get("reportId"),
            "geometry_cleanup_result_plan_source_mismatch",
        ),
    ]
    for field, expected_id, code in expected_ids:
        if cleanup_result.get(field) != expected_id:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "reports/geometry_cleanup_result.json",
                    f"Cleanup result {field} must match its source artifact.",
                )
            )
    if _nested_string(cleanup_result, ["integrity", "geometryCleanupResultHash"], "") != (
        hash_geometry_cleanup_result(cleanup_result)
    ):
        issues.append(
            _issue(
                "geometry_cleanup_result_hash_mismatch",
                "fatal",
                "reports/geometry_cleanup_result.json",
                "Cleanup result hash must match its canonical payload.",
            )
        )

    raw = proposal.get("rawProposal", {})
    input_asset = cleanup_result.get("inputAsset", {})
    output_asset = cleanup_result.get("outputAsset", {})
    execution = cleanup_result.get("execution", {})
    readiness = cleanup_result.get("readiness", {})
    policy = cleanup_result.get("policy", {})
    for name, block in [
        ("inputAsset", input_asset),
        ("outputAsset", output_asset),
        ("execution", execution),
        ("readiness", readiness),
        ("policy", policy),
    ]:
        if not isinstance(block, dict):
            issues.append(
                _issue(
                    "geometry_cleanup_result_block_invalid",
                    "fatal",
                    "reports/geometry_cleanup_result.json",
                    f"Cleanup result {name} block must be an object.",
                )
            )
            return

    source_asset_path = _validate_cleanup_result_asset_reference(
        package_dir,
        str(raw.get("assetPath", "")),
        input_asset,
        "geometry_cleanup_result_input_asset",
        issues,
    )
    output_asset_path = _validate_cleanup_result_asset_reference(
        package_dir,
        str(output_asset.get("path", "")),
        output_asset,
        "geometry_cleanup_result_output_asset",
        issues,
    )
    if (
        input_asset.get("path") != raw.get("assetPath")
        or input_asset.get("sourceAssetHash") != raw.get("sourceAssetHash")
        or input_asset.get("byteSize") != raw.get("byteSize")
    ):
        issues.append(
            _issue(
                "geometry_cleanup_result_input_asset_mismatch",
                "fatal",
                "reports/geometry_cleanup_result.json",
                "Cleanup result input asset must mirror the raw proposal asset.",
            )
        )
    if output_asset.get("canonicalUseAllowed") is not False:
        issues.append(
            _issue(
                "geometry_cleanup_result_output_acceptance_invalid",
                "fatal",
                "reports/geometry_cleanup_result.json",
                "Cleanup preview output cannot be accepted for canonical use.",
            )
        )
    if output_asset.get("purpose") != "non_canonical_cleanup_preview":
        issues.append(
            _issue(
                "geometry_cleanup_result_output_purpose_invalid",
                "fatal",
                "reports/geometry_cleanup_result.json",
                "Cleanup result output must be labelled as a non-canonical preview.",
            )
        )

    if source_asset_path is not None and output_asset_path is not None:
        with tempfile.TemporaryDirectory() as temp_dir:
            expected_output = Path(temp_dir) / "manual_cleanup_preview.glb"
            try:
                expected = build_geometry_cleanup_result(
                    garment_id=str(manifest.get("garmentId", "")),
                    garment_class=str(manifest.get("garmentClass", "")),
                    raw_geometry_proposal=proposal,
                    raw_topology_report=raw_topology,
                    cleanup_plan_report=cleanup_plan,
                    source_asset_path=source_asset_path,
                    output_asset_path=expected_output,
                    output_package_asset_path=str(output_asset.get("path", "")),
                )
            except Exception as exc:
                issues.append(
                    _issue(
                        "geometry_cleanup_result_recompute_failed",
                        "fatal",
                        "reports/geometry_cleanup_result.json",
                        str(exc),
                    )
                )
                return
        for key in [
            "topologyBefore",
            "topologyAfter",
            "outputAudit",
            "executedOperations",
            "deferredOperations",
            "execution",
            "readiness",
        ]:
            if cleanup_result.get(key) != expected.get(key):
                issues.append(
                    _issue(
                        "geometry_cleanup_result_recompute_mismatch",
                        "fatal",
                        "reports/geometry_cleanup_result.json",
                        f"Cleanup result field {key} is stale.",
                    )
                )
        if output_asset.get("sourceAssetHash") != expected["outputAsset"]["sourceAssetHash"]:
            issues.append(
                _issue(
                    "geometry_cleanup_result_output_asset_determinism_mismatch",
                    "fatal",
                    "proposals/manual_cleanup_preview.glb",
                    "Cleanup preview GLB does not match deterministic cleanup output.",
                )
            )
        if sha256_file(output_asset_path) != expected["outputAsset"]["sourceAssetHash"]:
            issues.append(
                _issue(
                    "geometry_cleanup_result_output_asset_hash_mismatch",
                    "fatal",
                    "proposals/manual_cleanup_preview.glb",
                    "Cleanup preview GLB hash is stale.",
                )
            )

    if (
        execution.get("cleanupRun") is not True
        or execution.get("repairRun") is not False
        or execution.get("retopologyRun") is not False
        or execution.get("semanticTransferRun") is not False
        or execution.get("simulationBindingRun") is not False
        or execution.get("outputAssetPath") != output_asset.get("path")
        or execution.get("outputAssetHash") != output_asset.get("sourceAssetHash")
    ):
        issues.append(
            _issue(
                "geometry_cleanup_result_execution_state_invalid",
                "fatal",
                "reports/geometry_cleanup_result.json",
                "Cleanup result must record only the local safe cleanup execution.",
            )
        )
    if (
        readiness.get("status") != "partial_cleanup_completed"
        or readiness.get("acceptedForCleanProposal") is not False
        or readiness.get("acceptedForCanonical") is not False
        or readiness.get("acceptedForSimulation") is not False
        or readiness.get("acceptedForRuntimeRender") is not False
    ):
        issues.append(
            _issue(
                "geometry_cleanup_result_clean_acceptance_invalid",
                "fatal",
                "reports/geometry_cleanup_result.json",
                "Partial cleanup results cannot accept clean/canonical/runtime geometry.",
            )
        )
    if (
        policy.get("allowExternalApis") is not False
        or policy.get("allowTrainingUse") is not False
        or policy.get("containsUserImagery") is not False
        or policy.get("containsPersonalBodyData") is not False
        or policy.get("approvedDomain") != "avatar_and_garment_only"
    ):
        issues.append(
            _issue(
                "geometry_cleanup_result_policy_violation",
                "fatal",
                "reports/geometry_cleanup_result.json",
                "Cleanup results cannot permit external APIs, training use or user data.",
            )
        )
    caps = manifest.get("capabilities", {})
    if isinstance(caps, dict) and caps.get("geometryCleanupExecutionAvailable") is not True:
        issues.append(
            _issue(
                "geometry_cleanup_execution_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest must declare local cleanup execution availability.",
            )
        )
    if _contains_nonfinite(cleanup_result):
        issues.append(
            _issue(
                "geometry_cleanup_result_nonfinite_numeric_value",
                "fatal",
                "reports/geometry_cleanup_result.json",
                "Cleanup result report must not contain NaN or Infinity.",
            )
        )


def _validate_cleanup_result_asset_reference(
    package_dir: Path,
    expected_path: str,
    asset: dict[str, Any],
    code_prefix: str,
    issues: list[ValidationIssue],
) -> Path | None:
    path_value = asset.get("path")
    if not isinstance(path_value, str):
        issues.append(
            _issue(
                f"{code_prefix}_path_invalid",
                "fatal",
                "reports/geometry_cleanup_result.json",
                "Cleanup result asset path must be package-relative.",
            )
        )
        return None
    try:
        validate_package_relpath(path_value)
    except ValueError:
        issues.append(
            _issue(
                f"{code_prefix}_path_invalid",
                "fatal",
                "reports/geometry_cleanup_result.json",
                "Cleanup result asset path is unsafe.",
            )
        )
        return None
    if expected_path and path_value != expected_path:
        issues.append(
            _issue(
                f"{code_prefix}_path_mismatch",
                "fatal",
                "reports/geometry_cleanup_result.json",
                "Cleanup result asset path does not match the expected source.",
            )
        )
    asset_path = package_dir / path_value
    if not asset_path.exists():
        issues.append(
            _issue(
                f"{code_prefix}_missing",
                "fatal",
                path_value,
                "Cleanup result asset is missing.",
            )
        )
        return None
    if asset.get("sourceAssetHash") != sha256_file(asset_path):
        issues.append(
            _issue(
                f"{code_prefix}_hash_mismatch",
                "fatal",
                "reports/geometry_cleanup_result.json",
                "Cleanup result asset hash is stale.",
            )
        )
    if asset.get("byteSize") != asset_path.stat().st_size:
        issues.append(
            _issue(
                f"{code_prefix}_size_mismatch",
                "fatal",
                "reports/geometry_cleanup_result.json",
                "Cleanup result asset byte size is stale.",
            )
        )
    return asset_path


def _validate_geometry_semantic_transfer(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    semantic = _read_required_json(package_dir, "semantic/garment_graph.json", issues)
    pattern = _read_required_json(package_dir, "pattern/pattern.json", issues)
    cleanup_result = _read_required_json(
        package_dir, "reports/geometry_cleanup_result.json", issues
    )
    semantic_transfer = _read_required_json(
        package_dir, "reports/geometry_semantic_transfer.json", issues
    )
    if semantic is None or pattern is None or cleanup_result is None or semantic_transfer is None:
        return

    if semantic_transfer.get("garmentId") != manifest.get("garmentId"):
        issues.append(
            _issue(
                "geometry_semantic_transfer_garment_mismatch",
                "fatal",
                "reports/geometry_semantic_transfer.json",
                "Semantic transfer must reference the package garment ID.",
            )
        )
    if semantic_transfer.get("garmentClass") != manifest.get("garmentClass"):
        issues.append(
            _issue(
                "geometry_semantic_transfer_class_mismatch",
                "fatal",
                "reports/geometry_semantic_transfer.json",
                "Semantic transfer must reference the package garment class.",
            )
        )
    if semantic_transfer.get("sourceGeometryCleanupResultId") != cleanup_result.get("reportId"):
        issues.append(
            _issue(
                "geometry_semantic_transfer_cleanup_result_source_mismatch",
                "fatal",
                "reports/geometry_semantic_transfer.json",
                "Semantic transfer must reference the cleanup result ID.",
            )
        )

    expected_hashes = [
        (
            "sourceGeometryCleanupResultHash",
            _nested_string(cleanup_result, ["integrity", "geometryCleanupResultHash"], ""),
            "geometry_semantic_transfer_cleanup_result_hash_mismatch",
        ),
        (
            "sourceSemanticGraphHash",
            _json_hash(semantic),
            "geometry_semantic_transfer_semantic_hash_mismatch",
        ),
        (
            "sourcePatternHash",
            _json_hash(pattern),
            "geometry_semantic_transfer_pattern_hash_mismatch",
        ),
    ]
    for field, expected_hash, code in expected_hashes:
        if semantic_transfer.get(field) != expected_hash:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "reports/geometry_semantic_transfer.json",
                    f"Semantic transfer {field} must match its source artifact.",
                )
            )
    if _nested_string(semantic_transfer, ["integrity", "geometrySemanticTransferHash"], "") != (
        hash_geometry_semantic_transfer_report(semantic_transfer)
    ):
        issues.append(
            _issue(
                "geometry_semantic_transfer_hash_mismatch",
                "fatal",
                "reports/geometry_semantic_transfer.json",
                "Semantic transfer hash must match its canonical payload.",
            )
        )

    input_asset = semantic_transfer.get("inputAsset", {})
    execution = semantic_transfer.get("execution", {})
    readiness = semantic_transfer.get("readiness", {})
    aggregate = semantic_transfer.get("aggregate", {})
    policy = semantic_transfer.get("policy", {})
    for name, block in [
        ("inputAsset", input_asset),
        ("execution", execution),
        ("readiness", readiness),
        ("aggregate", aggregate),
        ("policy", policy),
    ]:
        if not isinstance(block, dict):
            issues.append(
                _issue(
                    "geometry_semantic_transfer_block_invalid",
                    "fatal",
                    "reports/geometry_semantic_transfer.json",
                    f"Semantic transfer {name} block must be an object.",
                )
            )
            return

    cleanup_output = cleanup_result.get("outputAsset", {})
    cleanup_asset_path = _validate_semantic_transfer_asset_reference(
        package_dir,
        str(cleanup_output.get("path", "")),
        input_asset,
        issues,
    )
    if (
        input_asset.get("path") != cleanup_output.get("path")
        or input_asset.get("sourceAssetHash") != cleanup_output.get("sourceAssetHash")
        or input_asset.get("byteSize") != cleanup_output.get("byteSize")
    ):
        issues.append(
            _issue(
                "geometry_semantic_transfer_input_asset_mismatch",
                "fatal",
                "reports/geometry_semantic_transfer.json",
                "Semantic transfer input asset must mirror the cleanup preview output.",
            )
        )
    if (
        input_asset.get("canonicalUseAllowed") is not False
        or input_asset.get("purpose") != "non_canonical_cleanup_preview"
    ):
        issues.append(
            _issue(
                "geometry_semantic_transfer_input_asset_acceptance_invalid",
                "fatal",
                "reports/geometry_semantic_transfer.json",
                "Semantic transfer input must remain a non-canonical cleanup preview.",
            )
        )

    if cleanup_asset_path is not None:
        try:
            expected = build_geometry_semantic_transfer_report(
                garment_id=str(manifest.get("garmentId", "")),
                garment_class=str(manifest.get("garmentClass", "")),
                semantic_graph=semantic,
                pattern=pattern,
                cleanup_result_report=cleanup_result,
                cleanup_asset_path=cleanup_asset_path,
            )
        except Exception as exc:
            issues.append(
                _issue(
                    "geometry_semantic_transfer_recompute_failed",
                    "fatal",
                    "reports/geometry_semantic_transfer.json",
                    str(exc),
                )
            )
            return
        for key in [
            "topologySnapshot",
            "panelTransfers",
            "boundaryClassifications",
            "aggregate",
            "execution",
            "readiness",
            "quality",
        ]:
            if semantic_transfer.get(key) != expected.get(key):
                issues.append(
                    _issue(
                        "geometry_semantic_transfer_recompute_mismatch",
                        "fatal",
                        "reports/geometry_semantic_transfer.json",
                        f"Semantic transfer field {key} is stale.",
                    )
                )

    required_panels = set(REQUIRED_PANELS)
    panel_transfers = semantic_transfer.get("panelTransfers", [])
    transferred = {
        str(transfer.get("panelId"))
        for transfer in panel_transfers
        if isinstance(transfer, dict)
        and transfer.get("transferStatus") == "stable_panel_id_transferred"
    }
    if not required_panels.issubset(transferred):
        issues.append(
            _issue(
                "geometry_semantic_transfer_required_panel_missing",
                "fatal",
                "reports/geometry_semantic_transfer.json",
                "Semantic transfer must include every required T-shirt panel.",
            )
        )
    if int(aggregate.get("unclassifiedBoundaryEdgeCount", -1)) != 0:
        issues.append(
            _issue(
                "geometry_semantic_transfer_unclassified_boundary",
                "fatal",
                "reports/geometry_semantic_transfer.json",
                "Every cleanup-preview boundary edge must classify to a known pattern boundary.",
            )
        )
    if (
        execution.get("semanticTransferRun") is not True
        or execution.get("panelIdTransferRun") is not True
        or execution.get("boundaryClassificationRun") is not True
        or execution.get("repairRun") is not False
        or execution.get("retopologyRun") is not False
        or execution.get("simulationBindingRun") is not False
        or execution.get("uvTransferRun") is not False
        or execution.get("materialTransferRun") is not False
    ):
        issues.append(
            _issue(
                "geometry_semantic_transfer_execution_state_invalid",
                "fatal",
                "reports/geometry_semantic_transfer.json",
                "Semantic transfer may only claim panel and boundary classification in this pass.",
            )
        )
    if (
        readiness.get("acceptedForCleanProposal") is not False
        or readiness.get("acceptedForCanonical") is not False
        or readiness.get("acceptedForSimulation") is not False
        or readiness.get("acceptedForRuntimeRender") is not False
    ):
        issues.append(
            _issue(
                "geometry_semantic_transfer_acceptance_invalid",
                "fatal",
                "reports/geometry_semantic_transfer.json",
                "Semantic transfer cannot accept clean/canonical/runtime geometry.",
            )
        )
    if (
        policy.get("allowExternalApis") is not False
        or policy.get("allowTrainingUse") is not False
        or policy.get("containsUserImagery") is not False
        or policy.get("containsPersonalBodyData") is not False
        or policy.get("approvedDomain") != "avatar_and_garment_only"
    ):
        issues.append(
            _issue(
                "geometry_semantic_transfer_policy_violation",
                "fatal",
                "reports/geometry_semantic_transfer.json",
                "Semantic transfer cannot permit external APIs, training use or user data.",
            )
        )
    caps = manifest.get("capabilities", {})
    if isinstance(caps, dict):
        expected_caps = [
            ("geometrySemanticTransferAvailable", True),
            ("geometryBoundaryClassificationAvailable", True),
        ]
        for key, expected_enabled in expected_caps:
            if caps.get(key) is not expected_enabled:
                issues.append(
                    _issue(
                        "geometry_semantic_transfer_capability_missing",
                        "fatal",
                        "manifest.json",
                        f"Manifest capability {key} must be {expected_enabled!r}.",
                    )
                )
    if _contains_nonfinite(semantic_transfer):
        issues.append(
            _issue(
                "geometry_semantic_transfer_nonfinite_numeric_value",
                "fatal",
                "reports/geometry_semantic_transfer.json",
                "Semantic transfer report must not contain NaN or Infinity.",
            )
        )


def _validate_semantic_transfer_asset_reference(
    package_dir: Path,
    expected_path: str,
    asset: dict[str, Any],
    issues: list[ValidationIssue],
) -> Path | None:
    path_value = asset.get("path")
    if not isinstance(path_value, str):
        issues.append(
            _issue(
                "geometry_semantic_transfer_input_asset_path_invalid",
                "fatal",
                "reports/geometry_semantic_transfer.json",
                "Semantic transfer input path must be package-relative.",
            )
        )
        return None
    try:
        validate_package_relpath(path_value)
    except ValueError:
        issues.append(
            _issue(
                "geometry_semantic_transfer_input_asset_path_invalid",
                "fatal",
                "reports/geometry_semantic_transfer.json",
                "Semantic transfer input path is unsafe.",
            )
        )
        return None
    if expected_path and path_value != expected_path:
        issues.append(
            _issue(
                "geometry_semantic_transfer_input_asset_path_mismatch",
                "fatal",
                "reports/geometry_semantic_transfer.json",
                "Semantic transfer input path does not match cleanup output.",
            )
        )
    asset_path = package_dir / path_value
    if not asset_path.exists():
        issues.append(
            _issue(
                "geometry_semantic_transfer_input_asset_missing",
                "fatal",
                path_value,
                "Semantic transfer input asset is missing.",
            )
        )
        return None
    if asset.get("sourceAssetHash") != sha256_file(asset_path):
        issues.append(
            _issue(
                "geometry_semantic_transfer_input_asset_hash_mismatch",
                "fatal",
                "reports/geometry_semantic_transfer.json",
                "Semantic transfer input asset hash is stale.",
            )
        )
    if asset.get("byteSize") != asset_path.stat().st_size:
        issues.append(
            _issue(
                "geometry_semantic_transfer_input_asset_size_mismatch",
                "fatal",
                "reports/geometry_semantic_transfer.json",
                "Semantic transfer input asset byte size is stale.",
            )
        )
    return asset_path


def _validate_geometry_binding_candidate(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    cleanup_result = _read_required_json(
        package_dir, "reports/geometry_cleanup_result.json", issues
    )
    semantic_transfer = _read_required_json(
        package_dir, "reports/geometry_semantic_transfer.json", issues
    )
    simulation_manifest = _read_required_json(package_dir, "simulation/mesh_manifest.json", issues)
    binding_candidate = _read_required_json(
        package_dir, "reports/geometry_binding_candidate.json", issues
    )
    if (
        cleanup_result is None
        or semantic_transfer is None
        or simulation_manifest is None
        or binding_candidate is None
    ):
        return

    if binding_candidate.get("garmentId") != manifest.get("garmentId"):
        issues.append(
            _issue(
                "geometry_binding_candidate_garment_mismatch",
                "fatal",
                "reports/geometry_binding_candidate.json",
                "Binding candidate must reference the package garment ID.",
            )
        )
    if binding_candidate.get("garmentClass") != manifest.get("garmentClass"):
        issues.append(
            _issue(
                "geometry_binding_candidate_class_mismatch",
                "fatal",
                "reports/geometry_binding_candidate.json",
                "Binding candidate must reference the package garment class.",
            )
        )
    expected_sources = [
        (
            "sourceGeometrySemanticTransferId",
            semantic_transfer.get("reportId"),
            "geometry_binding_candidate_semantic_source_mismatch",
        ),
        (
            "sourceGeometryCleanupResultId",
            cleanup_result.get("reportId"),
            "geometry_binding_candidate_cleanup_result_source_mismatch",
        ),
    ]
    for field, expected_value, code in expected_sources:
        if binding_candidate.get(field) != expected_value:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "reports/geometry_binding_candidate.json",
                    f"Binding candidate {field} must match its source artifact.",
                )
            )
    expected_hashes = [
        (
            "sourceGeometrySemanticTransferHash",
            _nested_string(semantic_transfer, ["integrity", "geometrySemanticTransferHash"], ""),
            "geometry_binding_candidate_semantic_hash_mismatch",
        ),
        (
            "sourceGeometryCleanupResultHash",
            _nested_string(cleanup_result, ["integrity", "geometryCleanupResultHash"], ""),
            "geometry_binding_candidate_cleanup_result_hash_mismatch",
        ),
    ]
    for field, expected_hash, code in expected_hashes:
        if binding_candidate.get(field) != expected_hash:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "reports/geometry_binding_candidate.json",
                    f"Binding candidate {field} must match its source artifact.",
                )
            )
    if _nested_string(binding_candidate, ["integrity", "geometryBindingCandidateHash"], "") != (
        hash_geometry_binding_candidate_report(binding_candidate)
    ):
        issues.append(
            _issue(
                "geometry_binding_candidate_hash_mismatch",
                "fatal",
                "reports/geometry_binding_candidate.json",
                "Binding candidate hash must match its canonical payload.",
            )
        )

    input_asset = binding_candidate.get("inputCleanupAsset", {})
    target_simulation = binding_candidate.get("targetSimulationMesh", {})
    candidate_binding = binding_candidate.get("candidateBinding", {})
    execution = binding_candidate.get("execution", {})
    readiness = binding_candidate.get("readiness", {})
    aggregate = binding_candidate.get("aggregate", {})
    policy = binding_candidate.get("policy", {})
    for name, block in [
        ("inputCleanupAsset", input_asset),
        ("targetSimulationMesh", target_simulation),
        ("candidateBinding", candidate_binding),
        ("execution", execution),
        ("readiness", readiness),
        ("aggregate", aggregate),
        ("policy", policy),
    ]:
        if not isinstance(block, dict):
            issues.append(
                _issue(
                    "geometry_binding_candidate_block_invalid",
                    "fatal",
                    "reports/geometry_binding_candidate.json",
                    f"Binding candidate {name} block must be an object.",
                )
            )
            return

    semantic_input = semantic_transfer.get("inputAsset", {})
    cleanup_asset_path = _validate_binding_candidate_asset_reference(
        package_dir,
        str(semantic_input.get("path", "")),
        input_asset,
        issues,
    )
    if (
        input_asset.get("path") != semantic_input.get("path")
        or input_asset.get("sourceAssetHash") != semantic_input.get("sourceAssetHash")
        or input_asset.get("byteSize") != semantic_input.get("byteSize")
    ):
        issues.append(
            _issue(
                "geometry_binding_candidate_input_asset_mismatch",
                "fatal",
                "reports/geometry_binding_candidate.json",
                "Binding candidate input asset must mirror the semantic transfer input.",
            )
        )
    if (
        input_asset.get("canonicalUseAllowed") is not False
        or input_asset.get("purpose") != "non_canonical_cleanup_preview"
    ):
        issues.append(
            _issue(
                "geometry_binding_candidate_input_asset_acceptance_invalid",
                "fatal",
                "reports/geometry_binding_candidate.json",
                "Binding candidate input must remain a non-canonical cleanup preview.",
            )
        )

    if target_simulation.get("path") != "simulation/simulation_mesh.glb":
        issues.append(
            _issue(
                "geometry_binding_candidate_target_path_invalid",
                "fatal",
                "reports/geometry_binding_candidate.json",
                "Binding candidate target must be the canonical simulation mesh path.",
            )
        )
    if target_simulation.get("topologyHash") != simulation_manifest.get("topologyHash"):
        issues.append(
            _issue(
                "geometry_binding_candidate_sim_topology_hash_mismatch",
                "fatal",
                "reports/geometry_binding_candidate.json",
                "Binding candidate simulation topology hash is stale.",
            )
        )
    if target_simulation.get("contentHash") != simulation_manifest.get("contentHash"):
        issues.append(
            _issue(
                "geometry_binding_candidate_sim_content_hash_mismatch",
                "fatal",
                "reports/geometry_binding_candidate.json",
                "Binding candidate simulation content hash is stale.",
            )
        )

    if cleanup_asset_path is not None:
        try:
            simulation_mesh = _meshset_from_manifest(simulation_manifest)
            expected = build_geometry_binding_candidate_report(
                garment_id=str(manifest.get("garmentId", "")),
                garment_class=str(manifest.get("garmentClass", "")),
                semantic_transfer_report=semantic_transfer,
                cleanup_asset_path=cleanup_asset_path,
                simulation_mesh=simulation_mesh,
                simulation_mesh_path="simulation/simulation_mesh.glb",
            )
        except Exception as exc:
            issues.append(
                _issue(
                    "geometry_binding_candidate_recompute_failed",
                    "fatal",
                    "reports/geometry_binding_candidate.json",
                    str(exc),
                )
            )
            return
        for key in [
            "inputCleanupAsset",
            "targetSimulationMesh",
            "candidateBinding",
            "vertexMappings",
            "panelSummaries",
            "aggregate",
            "execution",
            "readiness",
            "quality",
        ]:
            if binding_candidate.get(key) != expected.get(key):
                issues.append(
                    _issue(
                        "geometry_binding_candidate_recompute_mismatch",
                        "fatal",
                        "reports/geometry_binding_candidate.json",
                        f"Binding candidate field {key} is stale.",
                    )
                )

    if int(aggregate.get("mappedVertexCount", -1)) <= 0:
        issues.append(
            _issue(
                "geometry_binding_candidate_empty",
                "fatal",
                "reports/geometry_binding_candidate.json",
                "Binding candidate must map at least one cleanup-preview vertex.",
            )
        )
    if int(aggregate.get("unmappedVertexCount", -1)) != 0:
        issues.append(
            _issue(
                "geometry_binding_candidate_unmapped_vertices",
                "fatal",
                "reports/geometry_binding_candidate.json",
                "Every cleanup-preview vertex must map to the simulation mesh in this fixture.",
            )
        )
    if float(aggregate.get("candidateCompleteness", -1.0)) != 1.0:
        issues.append(
            _issue(
                "geometry_binding_candidate_incomplete",
                "fatal",
                "reports/geometry_binding_candidate.json",
                "Binding candidate completeness must be 1.0 for the fixture.",
            )
        )
    if (
        execution.get("candidateBindingRun") is not True
        or execution.get("simulationBindingRun") is not False
        or execution.get("runtimeBindingWritten") is not False
        or execution.get("deformationValidationRun") is not False
        or execution.get("repairRun") is not False
        or execution.get("retopologyRun") is not False
        or execution.get("cleanProposalRun") is not False
    ):
        issues.append(
            _issue(
                "geometry_binding_candidate_execution_state_invalid",
                "fatal",
                "reports/geometry_binding_candidate.json",
                "Binding candidate may not claim runtime binding, repair or clean proposal output.",
            )
        )
    if (
        readiness.get("acceptedForCleanProposal") is not False
        or readiness.get("acceptedForCanonical") is not False
        or readiness.get("acceptedForSimulation") is not False
        or readiness.get("acceptedForRuntimeRender") is not False
    ):
        issues.append(
            _issue(
                "geometry_binding_candidate_acceptance_invalid",
                "fatal",
                "reports/geometry_binding_candidate.json",
                "Binding candidate cannot accept clean/canonical/runtime geometry.",
            )
        )
    if (
        policy.get("allowExternalApis") is not False
        or policy.get("allowTrainingUse") is not False
        or policy.get("containsUserImagery") is not False
        or policy.get("containsPersonalBodyData") is not False
        or policy.get("approvedDomain") != "avatar_and_garment_only"
    ):
        issues.append(
            _issue(
                "geometry_binding_candidate_policy_violation",
                "fatal",
                "reports/geometry_binding_candidate.json",
                "Binding candidate cannot permit external APIs, training use or user data.",
            )
        )
    caps = manifest.get("capabilities", {})
    if isinstance(caps, dict) and caps.get("geometryBindingCandidateAvailable") is not True:
        issues.append(
            _issue(
                "geometry_binding_candidate_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest capability geometryBindingCandidateAvailable must be true.",
            )
        )
    if _contains_nonfinite(binding_candidate):
        issues.append(
            _issue(
                "geometry_binding_candidate_nonfinite_numeric_value",
                "fatal",
                "reports/geometry_binding_candidate.json",
                "Binding candidate report must not contain NaN or Infinity.",
            )
        )


def _validate_binding_candidate_asset_reference(
    package_dir: Path,
    expected_path: str,
    asset: dict[str, Any],
    issues: list[ValidationIssue],
) -> Path | None:
    path_value = asset.get("path")
    if not isinstance(path_value, str):
        issues.append(
            _issue(
                "geometry_binding_candidate_input_asset_path_invalid",
                "fatal",
                "reports/geometry_binding_candidate.json",
                "Binding candidate input path must be package-relative.",
            )
        )
        return None
    try:
        validate_package_relpath(path_value)
    except ValueError:
        issues.append(
            _issue(
                "geometry_binding_candidate_input_asset_path_invalid",
                "fatal",
                "reports/geometry_binding_candidate.json",
                "Binding candidate input path is unsafe.",
            )
        )
        return None
    if expected_path and path_value != expected_path:
        issues.append(
            _issue(
                "geometry_binding_candidate_input_asset_path_mismatch",
                "fatal",
                "reports/geometry_binding_candidate.json",
                "Binding candidate input path does not match semantic transfer input.",
            )
        )
    asset_path = package_dir / path_value
    if not asset_path.exists():
        issues.append(
            _issue(
                "geometry_binding_candidate_input_asset_missing",
                "fatal",
                path_value,
                "Binding candidate input asset is missing.",
            )
        )
        return None
    if asset.get("sourceAssetHash") != sha256_file(asset_path):
        issues.append(
            _issue(
                "geometry_binding_candidate_input_asset_hash_mismatch",
                "fatal",
                "reports/geometry_binding_candidate.json",
                "Binding candidate input asset hash is stale.",
            )
        )
    if asset.get("byteSize") != asset_path.stat().st_size:
        issues.append(
            _issue(
                "geometry_binding_candidate_input_asset_size_mismatch",
                "fatal",
                "reports/geometry_binding_candidate.json",
                "Binding candidate input asset byte size is stale.",
            )
        )
    return asset_path


def _validate_geometry_binding_validation(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    cleanup_result = _read_required_json(
        package_dir, "reports/geometry_cleanup_result.json", issues
    )
    semantic_transfer = _read_required_json(
        package_dir, "reports/geometry_semantic_transfer.json", issues
    )
    binding_candidate = _read_required_json(
        package_dir, "reports/geometry_binding_candidate.json", issues
    )
    simulation_manifest = _read_required_json(package_dir, "simulation/mesh_manifest.json", issues)
    rest_state = _read_required_json(package_dir, "simulation/rest_state.json", issues)
    binding_validation = _read_required_json(
        package_dir, "reports/geometry_binding_validation.json", issues
    )
    if (
        cleanup_result is None
        or semantic_transfer is None
        or binding_candidate is None
        or simulation_manifest is None
        or rest_state is None
        or binding_validation is None
    ):
        return

    if binding_validation.get("garmentId") != manifest.get("garmentId"):
        issues.append(
            _issue(
                "geometry_binding_validation_garment_mismatch",
                "fatal",
                "reports/geometry_binding_validation.json",
                "Binding validation must reference the package garment ID.",
            )
        )
    if binding_validation.get("garmentClass") != manifest.get("garmentClass"):
        issues.append(
            _issue(
                "geometry_binding_validation_class_mismatch",
                "fatal",
                "reports/geometry_binding_validation.json",
                "Binding validation must reference the package garment class.",
            )
        )

    expected_sources = [
        (
            "sourceGeometryBindingCandidateId",
            binding_candidate.get("reportId"),
            "geometry_binding_validation_candidate_source_mismatch",
        ),
        (
            "sourceGeometrySemanticTransferId",
            semantic_transfer.get("reportId"),
            "geometry_binding_validation_semantic_source_mismatch",
        ),
        (
            "sourceGeometryCleanupResultId",
            cleanup_result.get("reportId"),
            "geometry_binding_validation_cleanup_result_source_mismatch",
        ),
    ]
    for field, expected_value, code in expected_sources:
        if binding_validation.get(field) != expected_value:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "reports/geometry_binding_validation.json",
                    f"Binding validation {field} must match its source artifact.",
                )
            )

    expected_hashes = [
        (
            "sourceGeometryBindingCandidateHash",
            _nested_string(binding_candidate, ["integrity", "geometryBindingCandidateHash"], ""),
            "geometry_binding_validation_candidate_hash_mismatch",
        ),
        (
            "sourceGeometrySemanticTransferHash",
            _nested_string(semantic_transfer, ["integrity", "geometrySemanticTransferHash"], ""),
            "geometry_binding_validation_semantic_hash_mismatch",
        ),
        (
            "sourceGeometryCleanupResultHash",
            _nested_string(cleanup_result, ["integrity", "geometryCleanupResultHash"], ""),
            "geometry_binding_validation_cleanup_result_hash_mismatch",
        ),
    ]
    for field, expected_hash, code in expected_hashes:
        if binding_validation.get(field) != expected_hash:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "reports/geometry_binding_validation.json",
                    f"Binding validation {field} must match its source artifact.",
                )
            )

    if _nested_string(binding_validation, ["integrity", "geometryBindingValidationHash"], "") != (
        hash_geometry_binding_validation_report(binding_validation)
    ):
        issues.append(
            _issue(
                "geometry_binding_validation_hash_mismatch",
                "fatal",
                "reports/geometry_binding_validation.json",
                "Binding validation hash must match its canonical payload.",
            )
        )

    input_asset = binding_validation.get("inputCleanupAsset", {})
    source_rest = binding_validation.get("sourceRestSimulation", {})
    target_settled = binding_validation.get("targetSettledSimulation", {})
    validation_settings = binding_validation.get("validationSettings", {})
    execution = binding_validation.get("execution", {})
    readiness = binding_validation.get("readiness", {})
    aggregate = binding_validation.get("aggregate", {})
    quality = binding_validation.get("quality", {})
    policy = binding_validation.get("policy", {})
    for name, block in [
        ("inputCleanupAsset", input_asset),
        ("sourceRestSimulation", source_rest),
        ("targetSettledSimulation", target_settled),
        ("validationSettings", validation_settings),
        ("execution", execution),
        ("readiness", readiness),
        ("aggregate", aggregate),
        ("quality", quality),
        ("policy", policy),
    ]:
        if not isinstance(block, dict):
            issues.append(
                _issue(
                    "geometry_binding_validation_block_invalid",
                    "fatal",
                    "reports/geometry_binding_validation.json",
                    f"Binding validation {name} block must be an object.",
                )
            )
            return

    candidate_asset = binding_candidate.get("inputCleanupAsset", {})
    cleanup_asset_path = _validate_binding_validation_asset_reference(
        package_dir,
        candidate_asset,
        input_asset,
        issues,
    )
    if source_rest.get("path") != "simulation/rest_state.json":
        issues.append(
            _issue(
                "geometry_binding_validation_rest_path_invalid",
                "fatal",
                "reports/geometry_binding_validation.json",
                "Binding validation rest source must reference simulation/rest_state.json.",
            )
        )
    if target_settled.get("path") != "simulation/simulation_mesh.glb":
        issues.append(
            _issue(
                "geometry_binding_validation_target_path_invalid",
                "fatal",
                "reports/geometry_binding_validation.json",
                "Binding validation target must reference simulation/simulation_mesh.glb.",
            )
        )

    try:
        settled_mesh = _meshset_from_manifest(simulation_manifest)
        rest_mesh = _meshset_from_state_and_manifest(rest_state, simulation_manifest)
    except Exception as exc:
        issues.append(
            _issue(
                "geometry_binding_validation_mesh_rebuild_failed",
                "fatal",
                "reports/geometry_binding_validation.json",
                str(exc),
            )
        )
        return

    if source_rest.get("topologyHash") != topology_hash(rest_mesh):
        issues.append(
            _issue(
                "geometry_binding_validation_rest_topology_hash_mismatch",
                "fatal",
                "reports/geometry_binding_validation.json",
                "Binding validation rest topology hash is stale.",
            )
        )
    if source_rest.get("contentHash") != geometry_content_hash(rest_mesh):
        issues.append(
            _issue(
                "geometry_binding_validation_rest_content_hash_mismatch",
                "fatal",
                "reports/geometry_binding_validation.json",
                "Binding validation rest content hash is stale.",
            )
        )
    if target_settled.get("topologyHash") != simulation_manifest.get("topologyHash"):
        issues.append(
            _issue(
                "geometry_binding_validation_settled_topology_hash_mismatch",
                "fatal",
                "reports/geometry_binding_validation.json",
                "Binding validation settled topology hash is stale.",
            )
        )
    if target_settled.get("contentHash") != simulation_manifest.get("contentHash"):
        issues.append(
            _issue(
                "geometry_binding_validation_settled_content_hash_mismatch",
                "fatal",
                "reports/geometry_binding_validation.json",
                "Binding validation settled content hash is stale.",
            )
        )

    if cleanup_asset_path is not None:
        try:
            expected = build_geometry_binding_validation_report(
                garment_id=str(manifest.get("garmentId", "")),
                garment_class=str(manifest.get("garmentClass", "")),
                binding_candidate_report=binding_candidate,
                cleanup_asset_path=cleanup_asset_path,
                rest_simulation_mesh=rest_mesh,
                settled_simulation_mesh=settled_mesh,
                rest_state_path="simulation/rest_state.json",
                settled_simulation_mesh_path="simulation/simulation_mesh.glb",
            )
        except Exception as exc:
            issues.append(
                _issue(
                    "geometry_binding_validation_recompute_failed",
                    "fatal",
                    "reports/geometry_binding_validation.json",
                    str(exc),
                )
            )
            return
        for key in [
            "inputCleanupAsset",
            "sourceRestSimulation",
            "targetSettledSimulation",
            "validationSettings",
            "validationRecords",
            "aggregate",
            "checks",
            "execution",
            "readiness",
            "quality",
        ]:
            if binding_validation.get(key) != expected.get(key):
                issues.append(
                    _issue(
                        "geometry_binding_validation_recompute_mismatch",
                        "fatal",
                        "reports/geometry_binding_validation.json",
                        f"Binding validation field {key} is stale.",
                    )
                )

    if int(aggregate.get("validationRecordCount", -1)) <= 0:
        issues.append(
            _issue(
                "geometry_binding_validation_empty",
                "fatal",
                "reports/geometry_binding_validation.json",
                "Binding validation must include per-vertex validation records.",
            )
        )
    if int(aggregate.get("unmappedVertexCount", -1)) != 0:
        issues.append(
            _issue(
                "geometry_binding_validation_unmapped_vertices",
                "fatal",
                "reports/geometry_binding_validation.json",
                "Every cleanup-preview vertex must remain mapped during validation.",
            )
        )
    if (
        execution.get("candidateBindingRun") is not True
        or execution.get("deformationValidationRun") is not True
        or execution.get("simulationBindingRun") is not False
        or execution.get("runtimeBindingWritten") is not False
        or execution.get("runtimeBindingAccepted") is not False
        or execution.get("repairRun") is not False
        or execution.get("retopologyRun") is not False
        or execution.get("cleanProposalRun") is not False
    ):
        issues.append(
            _issue(
                "geometry_binding_validation_execution_state_invalid",
                "fatal",
                "reports/geometry_binding_validation.json",
                (
                    "Binding validation may not claim runtime binding, repair "
                    "or clean proposal output."
                ),
            )
        )
    if (
        readiness.get("acceptedForCleanProposal") is not False
        or readiness.get("acceptedForCanonical") is not False
        or readiness.get("acceptedForSimulation") is not False
        or readiness.get("acceptedForRuntimeRender") is not False
    ):
        issues.append(
            _issue(
                "geometry_binding_validation_acceptance_invalid",
                "fatal",
                "reports/geometry_binding_validation.json",
                "Binding validation cannot accept clean/canonical/runtime geometry in D0.",
            )
        )
    if quality.get("status") != "failed_rejected":
        issues.append(
            _issue(
                "geometry_binding_validation_quality_status_invalid",
                "fatal",
                "reports/geometry_binding_validation.json",
                "D0 binding validation must remain a failed rejection report.",
            )
        )
    if (
        policy.get("allowExternalApis") is not False
        or policy.get("allowTrainingUse") is not False
        or policy.get("containsUserImagery") is not False
        or policy.get("containsPersonalBodyData") is not False
        or policy.get("approvedDomain") != "avatar_and_garment_only"
    ):
        issues.append(
            _issue(
                "geometry_binding_validation_policy_violation",
                "fatal",
                "reports/geometry_binding_validation.json",
                "Binding validation cannot permit external APIs, training use or user data.",
            )
        )
    caps = manifest.get("capabilities", {})
    if isinstance(caps, dict) and caps.get("geometryBindingValidationAvailable") is not True:
        issues.append(
            _issue(
                "geometry_binding_validation_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest capability geometryBindingValidationAvailable must be true.",
            )
        )
    if _contains_nonfinite(binding_validation):
        issues.append(
            _issue(
                "geometry_binding_validation_nonfinite_numeric_value",
                "fatal",
                "reports/geometry_binding_validation.json",
                "Binding validation report must not contain NaN or Infinity.",
            )
        )


def _validate_binding_validation_asset_reference(
    package_dir: Path,
    candidate_asset: dict[str, Any],
    asset: dict[str, Any],
    issues: list[ValidationIssue],
) -> Path | None:
    path_value = asset.get("path")
    if not isinstance(path_value, str):
        issues.append(
            _issue(
                "geometry_binding_validation_input_asset_path_invalid",
                "fatal",
                "reports/geometry_binding_validation.json",
                "Binding validation input path must be package-relative.",
            )
        )
        return None
    try:
        validate_package_relpath(path_value)
    except ValueError:
        issues.append(
            _issue(
                "geometry_binding_validation_input_asset_path_invalid",
                "fatal",
                "reports/geometry_binding_validation.json",
                "Binding validation input path is unsafe.",
            )
        )
        return None
    if (
        asset.get("path") != candidate_asset.get("path")
        or asset.get("sourceAssetHash") != candidate_asset.get("sourceAssetHash")
        or asset.get("byteSize") != candidate_asset.get("byteSize")
        or asset.get("canonicalUseAllowed") is not False
        or asset.get("purpose") != "non_canonical_cleanup_preview"
    ):
        issues.append(
            _issue(
                "geometry_binding_validation_input_asset_mismatch",
                "fatal",
                "reports/geometry_binding_validation.json",
                "Binding validation input asset must mirror the binding candidate input.",
            )
        )
    asset_path = package_dir / path_value
    if not asset_path.exists():
        issues.append(
            _issue(
                "geometry_binding_validation_input_asset_missing",
                "fatal",
                path_value,
                "Binding validation input asset is missing.",
            )
        )
        return None
    if asset.get("sourceAssetHash") != sha256_file(asset_path):
        issues.append(
            _issue(
                "geometry_binding_validation_input_asset_hash_mismatch",
                "fatal",
                "reports/geometry_binding_validation.json",
                "Binding validation input asset hash is stale.",
            )
        )
    if asset.get("byteSize") != asset_path.stat().st_size:
        issues.append(
            _issue(
                "geometry_binding_validation_input_asset_size_mismatch",
                "fatal",
                "reports/geometry_binding_validation.json",
                "Binding validation input asset byte size is stale.",
            )
        )
    return asset_path


def _validate_geometry_repair_retopology_plan(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    raw_topology = _read_required_json(package_dir, "reports/raw_geometry_topology.json", issues)
    cleanup_result = _read_required_json(
        package_dir, "reports/geometry_cleanup_result.json", issues
    )
    semantic_transfer = _read_required_json(
        package_dir, "reports/geometry_semantic_transfer.json", issues
    )
    binding_candidate = _read_required_json(
        package_dir, "reports/geometry_binding_candidate.json", issues
    )
    binding_validation = _read_required_json(
        package_dir, "reports/geometry_binding_validation.json", issues
    )
    repair_plan = _read_required_json(
        package_dir, "reports/geometry_repair_retopology_plan.json", issues
    )
    if (
        raw_topology is None
        or cleanup_result is None
        or semantic_transfer is None
        or binding_candidate is None
        or binding_validation is None
        or repair_plan is None
    ):
        return

    if repair_plan.get("garmentId") != manifest.get("garmentId"):
        issues.append(
            _issue(
                "geometry_repair_retopology_plan_garment_mismatch",
                "fatal",
                "reports/geometry_repair_retopology_plan.json",
                "Repair/retopology plan must reference the package garment ID.",
            )
        )
    if repair_plan.get("garmentClass") != manifest.get("garmentClass"):
        issues.append(
            _issue(
                "geometry_repair_retopology_plan_class_mismatch",
                "fatal",
                "reports/geometry_repair_retopology_plan.json",
                "Repair/retopology plan must reference the package garment class.",
            )
        )

    expected_sources = [
        (
            "sourceRawTopologyReportId",
            raw_topology.get("reportId"),
            "geometry_repair_retopology_plan_topology_source_mismatch",
        ),
        (
            "sourceGeometryCleanupResultId",
            cleanup_result.get("reportId"),
            "geometry_repair_retopology_plan_cleanup_result_source_mismatch",
        ),
        (
            "sourceGeometrySemanticTransferId",
            semantic_transfer.get("reportId"),
            "geometry_repair_retopology_plan_semantic_source_mismatch",
        ),
        (
            "sourceGeometryBindingCandidateId",
            binding_candidate.get("reportId"),
            "geometry_repair_retopology_plan_candidate_source_mismatch",
        ),
        (
            "sourceGeometryBindingValidationId",
            binding_validation.get("reportId"),
            "geometry_repair_retopology_plan_validation_source_mismatch",
        ),
    ]
    for field, expected_value, code in expected_sources:
        if repair_plan.get(field) != expected_value:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "reports/geometry_repair_retopology_plan.json",
                    f"Repair/retopology plan {field} must match its source artifact.",
                )
            )

    expected_hashes = [
        (
            "sourceRawTopologyReportHash",
            _nested_string(raw_topology, ["integrity", "rawGeometryTopologyReportHash"], ""),
            "geometry_repair_retopology_plan_topology_hash_mismatch",
        ),
        (
            "sourceGeometryCleanupResultHash",
            _nested_string(cleanup_result, ["integrity", "geometryCleanupResultHash"], ""),
            "geometry_repair_retopology_plan_cleanup_result_hash_mismatch",
        ),
        (
            "sourceGeometrySemanticTransferHash",
            _nested_string(semantic_transfer, ["integrity", "geometrySemanticTransferHash"], ""),
            "geometry_repair_retopology_plan_semantic_hash_mismatch",
        ),
        (
            "sourceGeometryBindingCandidateHash",
            _nested_string(binding_candidate, ["integrity", "geometryBindingCandidateHash"], ""),
            "geometry_repair_retopology_plan_candidate_hash_mismatch",
        ),
        (
            "sourceGeometryBindingValidationHash",
            _nested_string(binding_validation, ["integrity", "geometryBindingValidationHash"], ""),
            "geometry_repair_retopology_plan_validation_hash_mismatch",
        ),
    ]
    for field, expected_hash, code in expected_hashes:
        if repair_plan.get(field) != expected_hash:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "reports/geometry_repair_retopology_plan.json",
                    f"Repair/retopology plan {field} must match its source artifact.",
                )
            )

    if _nested_string(repair_plan, ["integrity", "geometryRepairRetopologyPlanHash"], "") != (
        hash_geometry_repair_retopology_plan(repair_plan)
    ):
        issues.append(
            _issue(
                "geometry_repair_retopology_plan_hash_mismatch",
                "fatal",
                "reports/geometry_repair_retopology_plan.json",
                "Repair/retopology plan hash must match its canonical payload.",
            )
        )

    try:
        expected = build_geometry_repair_retopology_plan(
            garment_id=str(manifest.get("garmentId", "")),
            garment_class=str(manifest.get("garmentClass", "")),
            raw_topology_report=raw_topology,
            cleanup_result_report=cleanup_result,
            semantic_transfer_report=semantic_transfer,
            binding_candidate_report=binding_candidate,
            binding_validation_report=binding_validation,
        )
    except Exception as exc:
        issues.append(
            _issue(
                "geometry_repair_retopology_plan_recompute_failed",
                "fatal",
                "reports/geometry_repair_retopology_plan.json",
                str(exc),
            )
        )
        return
    for key in [
        "failureSnapshot",
        "planningSettings",
        "recommendedOperations",
        "repairSequence",
        "aggregate",
        "execution",
        "readiness",
        "quality",
    ]:
        if repair_plan.get(key) != expected.get(key):
            issues.append(
                _issue(
                    "geometry_repair_retopology_plan_recompute_mismatch",
                    "fatal",
                    "reports/geometry_repair_retopology_plan.json",
                    f"Repair/retopology plan field {key} is stale.",
                )
            )

    failure_snapshot = repair_plan.get("failureSnapshot", {})
    aggregate = repair_plan.get("aggregate", {})
    operations = repair_plan.get("recommendedOperations", [])
    sequence = repair_plan.get("repairSequence", [])
    execution = repair_plan.get("execution", {})
    readiness = repair_plan.get("readiness", {})
    quality = repair_plan.get("quality", {})
    policy = repair_plan.get("policy", {})
    for name, block in [
        ("failureSnapshot", failure_snapshot),
        ("aggregate", aggregate),
        ("execution", execution),
        ("readiness", readiness),
        ("quality", quality),
        ("policy", policy),
    ]:
        if not isinstance(block, dict):
            issues.append(
                _issue(
                    "geometry_repair_retopology_plan_block_invalid",
                    "fatal",
                    "reports/geometry_repair_retopology_plan.json",
                    f"Repair/retopology plan {name} block must be an object.",
                )
            )
            return
    if not isinstance(operations, list) or not isinstance(sequence, list):
        issues.append(
            _issue(
                "geometry_repair_retopology_plan_block_invalid",
                "fatal",
                "reports/geometry_repair_retopology_plan.json",
                "Repair/retopology plan operations and sequence must be arrays.",
            )
        )
        return

    required_count = sum(
        1 for operation in operations if isinstance(operation, dict) and operation.get("required")
    )
    if (
        int(aggregate.get("recommendedOperationCount", -1)) != len(operations)
        or int(aggregate.get("requiredOperationCount", -1)) != required_count
        or int(aggregate.get("repairSequenceStepCount", -1)) != len(sequence)
    ):
        issues.append(
            _issue(
                "geometry_repair_retopology_plan_aggregate_invalid",
                "fatal",
                "reports/geometry_repair_retopology_plan.json",
                "Repair/retopology plan aggregate counts must match operations and sequence.",
            )
        )
    if int(failure_snapshot.get("deformationFailedVertexCount", 0)) <= 0:
        issues.append(
            _issue(
                "geometry_repair_retopology_plan_missing_failure_evidence",
                "fatal",
                "reports/geometry_repair_retopology_plan.json",
                "Repair/retopology plan must preserve deformation failure evidence.",
            )
        )
    if (
        execution.get("repairRetopologyPlanGenerated") is not True
        or execution.get("repairRun") is not False
        or execution.get("retopologyRun") is not False
        or execution.get("seamSplitRun") is not False
        or execution.get("normalContinuityValidationRun") is not False
        or execution.get("tangentContinuityValidationRun") is not False
        or execution.get("runtimeBindingWritten") is not False
        or execution.get("runtimeBindingAccepted") is not False
        or execution.get("cleanProposalRun") is not False
    ):
        issues.append(
            _issue(
                "geometry_repair_retopology_plan_execution_state_invalid",
                "fatal",
                "reports/geometry_repair_retopology_plan.json",
                "Repair/retopology plan may not claim execution, runtime binding or clean output.",
            )
        )
    if (
        readiness.get("acceptedForCleanProposal") is not False
        or readiness.get("acceptedForCanonical") is not False
        or readiness.get("acceptedForSimulation") is not False
        or readiness.get("acceptedForRuntimeRender") is not False
    ):
        issues.append(
            _issue(
                "geometry_repair_retopology_plan_acceptance_invalid",
                "fatal",
                "reports/geometry_repair_retopology_plan.json",
                "Repair/retopology plan cannot accept clean/canonical/runtime geometry in D0.",
            )
        )
    if quality.get("status") != "plan_only_rejected":
        issues.append(
            _issue(
                "geometry_repair_retopology_plan_quality_status_invalid",
                "fatal",
                "reports/geometry_repair_retopology_plan.json",
                "D0 repair/retopology plan must remain a rejected plan-only artifact.",
            )
        )
    if (
        policy.get("allowExternalApis") is not False
        or policy.get("allowTrainingUse") is not False
        or policy.get("containsUserImagery") is not False
        or policy.get("containsPersonalBodyData") is not False
        or policy.get("approvedDomain") != "avatar_and_garment_only"
    ):
        issues.append(
            _issue(
                "geometry_repair_retopology_plan_policy_violation",
                "fatal",
                "reports/geometry_repair_retopology_plan.json",
                "Repair/retopology plan cannot permit external APIs, training use or user data.",
            )
        )
    caps = manifest.get("capabilities", {})
    if isinstance(caps, dict) and caps.get("geometryRepairRetopologyPlanAvailable") is not True:
        issues.append(
            _issue(
                "geometry_repair_retopology_plan_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest capability geometryRepairRetopologyPlanAvailable must be true.",
            )
        )
    if _contains_nonfinite(repair_plan):
        issues.append(
            _issue(
                "geometry_repair_retopology_plan_nonfinite_numeric_value",
                "fatal",
                "reports/geometry_repair_retopology_plan.json",
                "Repair/retopology plan must not contain NaN or Infinity.",
            )
        )


def _validate_geometry_repair_result(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    repair_plan = _read_required_json(
        package_dir, "reports/geometry_repair_retopology_plan.json", issues
    )
    binding_candidate = _read_required_json(
        package_dir, "reports/geometry_binding_candidate.json", issues
    )
    binding_validation = _read_required_json(
        package_dir, "reports/geometry_binding_validation.json", issues
    )
    simulation_manifest = _read_required_json(package_dir, "simulation/mesh_manifest.json", issues)
    repair_result = _read_required_json(package_dir, "reports/geometry_repair_result.json", issues)
    if (
        repair_plan is None
        or binding_candidate is None
        or binding_validation is None
        or simulation_manifest is None
        or repair_result is None
    ):
        return

    if repair_result.get("garmentId") != manifest.get("garmentId"):
        issues.append(
            _issue(
                "geometry_repair_result_garment_mismatch",
                "fatal",
                "reports/geometry_repair_result.json",
                "Repair result must reference the package garment ID.",
            )
        )
    if repair_result.get("garmentClass") != manifest.get("garmentClass"):
        issues.append(
            _issue(
                "geometry_repair_result_class_mismatch",
                "fatal",
                "reports/geometry_repair_result.json",
                "Repair result must reference the package garment class.",
            )
        )

    expected_sources = [
        (
            "sourceGeometryRepairRetopologyPlanId",
            repair_plan.get("reportId"),
            "geometry_repair_result_plan_source_mismatch",
        ),
        (
            "sourceGeometryBindingCandidateId",
            binding_candidate.get("reportId"),
            "geometry_repair_result_candidate_source_mismatch",
        ),
        (
            "sourceGeometryBindingValidationId",
            binding_validation.get("reportId"),
            "geometry_repair_result_validation_source_mismatch",
        ),
    ]
    for field, expected_value, code in expected_sources:
        if repair_result.get(field) != expected_value:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "reports/geometry_repair_result.json",
                    f"Repair result {field} must match its source artifact.",
                )
            )

    expected_hashes = [
        (
            "sourceGeometryRepairRetopologyPlanHash",
            _nested_string(repair_plan, ["integrity", "geometryRepairRetopologyPlanHash"], ""),
            "geometry_repair_result_plan_hash_mismatch",
        ),
        (
            "sourceGeometryBindingCandidateHash",
            _nested_string(binding_candidate, ["integrity", "geometryBindingCandidateHash"], ""),
            "geometry_repair_result_candidate_hash_mismatch",
        ),
        (
            "sourceGeometryBindingValidationHash",
            _nested_string(binding_validation, ["integrity", "geometryBindingValidationHash"], ""),
            "geometry_repair_result_validation_hash_mismatch",
        ),
    ]
    for field, expected_hash, code in expected_hashes:
        if repair_result.get(field) != expected_hash:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "reports/geometry_repair_result.json",
                    f"Repair result {field} must match its source artifact.",
                )
            )

    if _nested_string(repair_result, ["integrity", "geometryRepairResultHash"], "") != (
        hash_geometry_repair_result(repair_result)
    ):
        issues.append(
            _issue(
                "geometry_repair_result_hash_mismatch",
                "fatal",
                "reports/geometry_repair_result.json",
                "Repair result hash must match its canonical payload.",
            )
        )

    input_asset = repair_result.get("inputCleanupAsset", {})
    target_settled = repair_result.get("targetSettledSimulation", {})
    output_asset = repair_result.get("outputAsset", {})
    output_mesh = repair_result.get("outputMesh", {})
    metrics = repair_result.get("repairMetrics", {})
    aggregate = repair_result.get("aggregate", {})
    execution = repair_result.get("execution", {})
    readiness = repair_result.get("readiness", {})
    quality = repair_result.get("quality", {})
    policy = repair_result.get("policy", {})
    for name, block in [
        ("inputCleanupAsset", input_asset),
        ("targetSettledSimulation", target_settled),
        ("outputAsset", output_asset),
        ("outputMesh", output_mesh),
        ("repairMetrics", metrics),
        ("aggregate", aggregate),
        ("execution", execution),
        ("readiness", readiness),
        ("quality", quality),
        ("policy", policy),
    ]:
        if not isinstance(block, dict):
            issues.append(
                _issue(
                    "geometry_repair_result_block_invalid",
                    "fatal",
                    "reports/geometry_repair_result.json",
                    f"Repair result {name} block must be an object.",
                )
            )
            return

    candidate_asset = binding_candidate.get("inputCleanupAsset", {})
    cleanup_asset_path = _validate_repair_result_asset_reference(
        package_dir,
        str(candidate_asset.get("path", "")),
        input_asset,
        "geometry_repair_result_input_asset",
        issues,
    )
    output_asset_path = _validate_repair_result_asset_reference(
        package_dir,
        "proposals/manual_repair_preview.glb",
        output_asset,
        "geometry_repair_result_output_asset",
        issues,
    )
    if input_asset.get("sourceAssetHash") != candidate_asset.get("sourceAssetHash"):
        issues.append(
            _issue(
                "geometry_repair_result_input_asset_hash_mismatch",
                "fatal",
                "reports/geometry_repair_result.json",
                "Repair result input cleanup asset hash must mirror the binding candidate.",
            )
        )
    if input_asset.get("path") != binding_validation.get("inputCleanupAsset", {}).get("path"):
        issues.append(
            _issue(
                "geometry_repair_result_input_asset_mismatch",
                "fatal",
                "reports/geometry_repair_result.json",
                "Repair result input cleanup asset must mirror binding validation.",
            )
        )
    if output_asset.get("canonicalUseAllowed") is not False:
        issues.append(
            _issue(
                "geometry_repair_result_output_acceptance_invalid",
                "fatal",
                "reports/geometry_repair_result.json",
                "Repair preview output cannot be accepted for canonical use.",
            )
        )
    if output_asset.get("purpose") != "non_canonical_repair_reprojection_preview":
        issues.append(
            _issue(
                "geometry_repair_result_output_purpose_invalid",
                "fatal",
                "reports/geometry_repair_result.json",
                "Repair result output must be labelled as a non-canonical reprojection preview.",
            )
        )
    if target_settled.get("path") != "simulation/simulation_mesh.glb":
        issues.append(
            _issue(
                "geometry_repair_result_target_path_invalid",
                "fatal",
                "reports/geometry_repair_result.json",
                "Repair result target must reference simulation/simulation_mesh.glb.",
            )
        )

    try:
        settled_mesh = _meshset_from_manifest(simulation_manifest)
    except Exception as exc:
        issues.append(
            _issue(
                "geometry_repair_result_mesh_rebuild_failed",
                "fatal",
                "reports/geometry_repair_result.json",
                str(exc),
            )
        )
        return

    if target_settled.get("topologyHash") != topology_hash(settled_mesh):
        issues.append(
            _issue(
                "geometry_repair_result_target_topology_hash_mismatch",
                "fatal",
                "reports/geometry_repair_result.json",
                "Repair result settled simulation topology hash is stale.",
            )
        )
    if target_settled.get("contentHash") != geometry_content_hash(settled_mesh):
        issues.append(
            _issue(
                "geometry_repair_result_target_content_hash_mismatch",
                "fatal",
                "reports/geometry_repair_result.json",
                "Repair result settled simulation content hash is stale.",
            )
        )

    if cleanup_asset_path is not None and output_asset_path is not None:
        expected_output_hash = ""
        with tempfile.TemporaryDirectory() as temp_dir:
            expected_output = Path(temp_dir) / "manual_repair_preview.glb"
            try:
                expected_mesh = reproject_cleanup_preview_to_settled_simulation(
                    cleanup_asset_path=cleanup_asset_path,
                    binding_candidate_report=binding_candidate,
                    settled_simulation_mesh=settled_mesh,
                )
                write_indexed_glb(
                    expected_output,
                    expected_mesh,
                    "closy_partial_repair_reprojection_preview_v1",
                    (0.68, 0.78, 0.92, 1.0),
                )
                expected = build_geometry_repair_result_report(
                    garment_id=str(manifest.get("garmentId", "")),
                    garment_class=str(manifest.get("garmentClass", "")),
                    repair_retopology_plan_report=repair_plan,
                    binding_candidate_report=binding_candidate,
                    binding_validation_report=binding_validation,
                    cleanup_asset_path=cleanup_asset_path,
                    output_asset_path=expected_output,
                    output_package_asset_path=str(output_asset.get("path", "")),
                    output_mesh=expected_mesh,
                    settled_simulation_mesh=settled_mesh,
                    settled_simulation_mesh_path="simulation/simulation_mesh.glb",
                )
                expected_output_hash = sha256_file(expected_output)
            except Exception as exc:
                issues.append(
                    _issue(
                        "geometry_repair_result_recompute_failed",
                        "fatal",
                        "reports/geometry_repair_result.json",
                        str(exc),
                    )
                )
                return
        for key in [
            "inputCleanupAsset",
            "targetSettledSimulation",
            "outputAsset",
            "outputMesh",
            "repairMetrics",
            "executedOperations",
            "deferredOperations",
            "aggregate",
            "execution",
            "readiness",
            "quality",
        ]:
            if repair_result.get(key) != expected.get(key):
                issues.append(
                    _issue(
                        "geometry_repair_result_recompute_mismatch",
                        "fatal",
                        "reports/geometry_repair_result.json",
                        f"Repair result field {key} is stale.",
                    )
                )
        if output_asset.get("sourceAssetHash") != expected_output_hash:
            issues.append(
                _issue(
                    "geometry_repair_result_output_asset_determinism_mismatch",
                    "fatal",
                    "proposals/manual_repair_preview.glb",
                    "Repair preview GLB does not match deterministic reprojection output.",
                )
            )
        if sha256_file(output_asset_path) != expected_output_hash:
            issues.append(
                _issue(
                    "geometry_repair_result_output_asset_hash_mismatch",
                    "fatal",
                    "proposals/manual_repair_preview.glb",
                    "Repair preview GLB hash is stale.",
                )
            )

    if (
        execution.get("repairResultGenerated") is not True
        or execution.get("deformationReprojectionRun") is not True
        or execution.get("repairRun") is not True
        or execution.get("retopologyRun") is not False
        or execution.get("seamSplitRun") is not False
        or execution.get("componentStitchingRun") is not False
        or execution.get("normalContinuityValidationRun") is not False
        or execution.get("tangentContinuityValidationRun") is not False
        or execution.get("runtimeBindingWritten") is not False
        or execution.get("runtimeBindingAccepted") is not False
        or execution.get("cleanProposalRun") is not False
    ):
        issues.append(
            _issue(
                "geometry_repair_result_execution_state_invalid",
                "fatal",
                "reports/geometry_repair_result.json",
                "Partial repair result may only claim deformation reprojection execution.",
            )
        )
    if (
        readiness.get("status") != "partial_repair_completed_retopology_pending"
        or readiness.get("acceptedForCleanProposal") is not False
        or readiness.get("acceptedForCanonical") is not False
        or readiness.get("acceptedForSimulation") is not False
        or readiness.get("acceptedForRuntimeRender") is not False
    ):
        issues.append(
            _issue(
                "geometry_repair_result_acceptance_invalid",
                "fatal",
                "reports/geometry_repair_result.json",
                "Partial repair results cannot accept clean/canonical/runtime geometry.",
            )
        )
    if quality.get("status") != "partial_repair_rejected":
        issues.append(
            _issue(
                "geometry_repair_result_quality_status_invalid",
                "fatal",
                "reports/geometry_repair_result.json",
                "D0 repair result must remain rejected until retopology and binding pass.",
            )
        )
    if (
        int(aggregate.get("executedOperationCount", -1)) != 1
        or int(aggregate.get("deferredOperationCount", -1)) <= 0
        or int(aggregate.get("movedVertexCount", -1)) <= 0
        or aggregate.get("deformationOffsetReduced") is not True
    ):
        issues.append(
            _issue(
                "geometry_repair_result_aggregate_invalid",
                "fatal",
                "reports/geometry_repair_result.json",
                "Partial repair result aggregate must record one reprojection and deferred work.",
            )
        )
    if (
        policy.get("allowExternalApis") is not False
        or policy.get("allowTrainingUse") is not False
        or policy.get("containsUserImagery") is not False
        or policy.get("containsPersonalBodyData") is not False
        or policy.get("approvedDomain") != "avatar_and_garment_only"
    ):
        issues.append(
            _issue(
                "geometry_repair_result_policy_violation",
                "fatal",
                "reports/geometry_repair_result.json",
                "Repair result cannot permit external APIs, training use or user data.",
            )
        )
    caps = manifest.get("capabilities", {})
    if isinstance(caps, dict) and caps.get("geometryRepairResultAvailable") is not True:
        issues.append(
            _issue(
                "geometry_repair_result_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest capability geometryRepairResultAvailable must be true.",
            )
        )
    if _contains_nonfinite(repair_result):
        issues.append(
            _issue(
                "geometry_repair_result_nonfinite_numeric_value",
                "fatal",
                "reports/geometry_repair_result.json",
                "Repair result must not contain NaN or Infinity.",
            )
        )


def _validate_repair_result_asset_reference(
    package_dir: Path,
    expected_path: str,
    asset: dict[str, Any],
    code_prefix: str,
    issues: list[ValidationIssue],
) -> Path | None:
    path_value = asset.get("path")
    if not isinstance(path_value, str):
        issues.append(
            _issue(
                f"{code_prefix}_path_invalid",
                "fatal",
                "reports/geometry_repair_result.json",
                "Repair result asset path must be package-relative.",
            )
        )
        return None
    try:
        validate_package_relpath(path_value)
    except ValueError:
        issues.append(
            _issue(
                f"{code_prefix}_path_invalid",
                "fatal",
                "reports/geometry_repair_result.json",
                "Repair result asset path is unsafe.",
            )
        )
        return None
    if expected_path and path_value != expected_path:
        issues.append(
            _issue(
                f"{code_prefix}_path_mismatch",
                "fatal",
                "reports/geometry_repair_result.json",
                "Repair result asset path does not match the expected source.",
            )
        )
    asset_path = package_dir / path_value
    if not asset_path.exists():
        issues.append(
            _issue(
                f"{code_prefix}_missing",
                "fatal",
                path_value,
                "Repair result asset is missing.",
            )
        )
        return None
    if asset.get("sourceAssetHash") != sha256_file(asset_path):
        issues.append(
            _issue(
                f"{code_prefix}_hash_mismatch",
                "fatal",
                "reports/geometry_repair_result.json",
                "Repair result asset hash is stale.",
            )
        )
    if asset.get("byteSize") != asset_path.stat().st_size:
        issues.append(
            _issue(
                f"{code_prefix}_size_mismatch",
                "fatal",
                "reports/geometry_repair_result.json",
                "Repair result asset byte size is stale.",
            )
        )
    return asset_path


def _validate_geometry_runtime_binding_result(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    semantic_transfer = _read_required_json(
        package_dir, "reports/geometry_semantic_transfer.json", issues
    )
    binding_candidate = _read_required_json(
        package_dir, "reports/geometry_binding_candidate.json", issues
    )
    binding_validation = _read_required_json(
        package_dir, "reports/geometry_binding_validation.json", issues
    )
    repair_result = _read_required_json(package_dir, "reports/geometry_repair_result.json", issues)
    simulation_manifest = _read_required_json(package_dir, "simulation/mesh_manifest.json", issues)
    constraints = _read_required_json(package_dir, "simulation/constraints.json", issues)
    proposal_binding_manifest = _read_required_json(
        package_dir, "binding/proposal_binding_manifest.json", issues
    )
    runtime_result = _read_required_json(
        package_dir, "reports/geometry_runtime_binding_result.json", issues
    )
    if (
        semantic_transfer is None
        or binding_candidate is None
        or binding_validation is None
        or repair_result is None
        or simulation_manifest is None
        or constraints is None
        or proposal_binding_manifest is None
        or runtime_result is None
    ):
        return

    if runtime_result.get("garmentId") != manifest.get("garmentId"):
        issues.append(
            _issue(
                "geometry_runtime_binding_result_garment_mismatch",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime binding result must reference the package garment ID.",
            )
        )
    if runtime_result.get("garmentClass") != manifest.get("garmentClass"):
        issues.append(
            _issue(
                "geometry_runtime_binding_result_class_mismatch",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime binding result must reference the package garment class.",
            )
        )

    expected_sources = [
        (
            "sourceGeometryRepairResultId",
            repair_result.get("reportId"),
            "geometry_runtime_binding_result_repair_source_mismatch",
        ),
        (
            "sourceGeometrySemanticTransferId",
            semantic_transfer.get("reportId"),
            "geometry_runtime_binding_result_semantic_source_mismatch",
        ),
        (
            "sourceGeometryBindingCandidateId",
            binding_candidate.get("reportId"),
            "geometry_runtime_binding_result_candidate_source_mismatch",
        ),
        (
            "sourceGeometryBindingValidationId",
            binding_validation.get("reportId"),
            "geometry_runtime_binding_result_validation_source_mismatch",
        ),
    ]
    for field, expected_value, code in expected_sources:
        if runtime_result.get(field) != expected_value:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "reports/geometry_runtime_binding_result.json",
                    f"Runtime binding result {field} must match its source artifact.",
                )
            )

    expected_hashes = [
        (
            "sourceGeometryRepairResultHash",
            _nested_string(repair_result, ["integrity", "geometryRepairResultHash"], ""),
            "geometry_runtime_binding_result_repair_hash_mismatch",
        ),
        (
            "sourceGeometrySemanticTransferHash",
            _nested_string(semantic_transfer, ["integrity", "geometrySemanticTransferHash"], ""),
            "geometry_runtime_binding_result_semantic_hash_mismatch",
        ),
        (
            "sourceGeometryBindingCandidateHash",
            _nested_string(binding_candidate, ["integrity", "geometryBindingCandidateHash"], ""),
            "geometry_runtime_binding_result_candidate_hash_mismatch",
        ),
        (
            "sourceGeometryBindingValidationHash",
            _nested_string(binding_validation, ["integrity", "geometryBindingValidationHash"], ""),
            "geometry_runtime_binding_result_validation_hash_mismatch",
        ),
    ]
    for field, expected_hash, code in expected_hashes:
        if runtime_result.get(field) != expected_hash:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "reports/geometry_runtime_binding_result.json",
                    f"Runtime binding result {field} must match its source artifact.",
                )
            )

    if _nested_string(
        runtime_result, ["integrity", "geometryRuntimeBindingResultHash"], ""
    ) != hash_geometry_runtime_binding_result(runtime_result):
        issues.append(
            _issue(
                "geometry_runtime_binding_result_hash_mismatch",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime binding result hash must match its canonical payload.",
            )
        )

    input_repair_asset = runtime_result.get("inputRepairAsset", {})
    target_settled = runtime_result.get("targetSettledSimulation", {})
    output_render_asset = runtime_result.get("outputRenderAsset", {})
    output_binding = runtime_result.get("outputBinding", {})
    output_binding_manifest = runtime_result.get("outputBindingManifest", {})
    output_render_mesh = runtime_result.get("outputRenderMesh", {})
    retopology = runtime_result.get("retopology", {})
    seam_continuity = runtime_result.get("seamContinuity", {})
    aggregate = runtime_result.get("aggregate", {})
    execution = runtime_result.get("execution", {})
    readiness = runtime_result.get("readiness", {})
    quality = runtime_result.get("quality", {})
    policy = runtime_result.get("policy", {})
    for name, block in [
        ("inputRepairAsset", input_repair_asset),
        ("targetSettledSimulation", target_settled),
        ("outputRenderAsset", output_render_asset),
        ("outputBinding", output_binding),
        ("outputBindingManifest", output_binding_manifest),
        ("outputRenderMesh", output_render_mesh),
        ("retopology", retopology),
        ("seamContinuity", seam_continuity),
        ("aggregate", aggregate),
        ("execution", execution),
        ("readiness", readiness),
        ("quality", quality),
        ("policy", policy),
    ]:
        if not isinstance(block, dict):
            issues.append(
                _issue(
                    "geometry_runtime_binding_result_block_invalid",
                    "fatal",
                    "reports/geometry_runtime_binding_result.json",
                    f"Runtime binding result {name} block must be an object.",
                )
            )
            return

    _validate_runtime_binding_result_file_reference(
        package_dir,
        "proposals/manual_repair_preview.glb",
        input_repair_asset,
        "geometry_runtime_binding_result_input_repair_asset",
        issues,
    )
    output_render_asset_path = _validate_runtime_binding_result_file_reference(
        package_dir,
        "proposals/manual_runtime_retopology_preview.glb",
        output_render_asset,
        "geometry_runtime_binding_result_output_render_asset",
        issues,
    )
    output_binding_path = _validate_runtime_binding_result_file_reference(
        package_dir,
        "binding/proposal_sim_to_render.bin",
        output_binding,
        "geometry_runtime_binding_result_output_binding",
        issues,
    )
    if input_repair_asset.get("sourceAssetHash") != repair_result.get("outputAsset", {}).get(
        "sourceAssetHash"
    ):
        issues.append(
            _issue(
                "geometry_runtime_binding_result_repair_asset_hash_mismatch",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime binding input repair asset hash must mirror the repair result.",
            )
        )
    if input_repair_asset.get("purpose") != repair_result.get("outputAsset", {}).get("purpose"):
        issues.append(
            _issue(
                "geometry_runtime_binding_result_repair_asset_purpose_mismatch",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime binding input repair asset purpose must mirror the repair result.",
            )
        )

    try:
        settled_mesh = _meshset_from_manifest(simulation_manifest)
    except Exception as exc:
        issues.append(
            _issue(
                "geometry_runtime_binding_result_mesh_rebuild_failed",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                str(exc),
            )
        )
        return
    if target_settled.get("path") != "simulation/simulation_mesh.glb":
        issues.append(
            _issue(
                "geometry_runtime_binding_result_target_path_invalid",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime binding result target must reference simulation/simulation_mesh.glb.",
            )
        )
    if target_settled.get("topologyHash") != topology_hash(settled_mesh):
        issues.append(
            _issue(
                "geometry_runtime_binding_result_target_topology_hash_mismatch",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime binding settled simulation topology hash is stale.",
            )
        )
    if target_settled.get("contentHash") != geometry_content_hash(settled_mesh):
        issues.append(
            _issue(
                "geometry_runtime_binding_result_target_content_hash_mismatch",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime binding settled simulation content hash is stale.",
            )
        )

    if output_render_asset.get("canonicalUseAllowed") is not False:
        issues.append(
            _issue(
                "geometry_runtime_binding_result_render_acceptance_invalid",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime retopology preview cannot be accepted for canonical use.",
            )
        )
    if output_render_asset.get("runtimePreviewUseAllowed") is not True:
        issues.append(
            _issue(
                "geometry_runtime_binding_result_runtime_preview_invalid",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime retopology preview must be accepted only for preview/runtime inspection.",
            )
        )
    if output_render_asset.get("purpose") != "non_canonical_runtime_retopology_preview":
        issues.append(
            _issue(
                "geometry_runtime_binding_result_render_purpose_invalid",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime retopology preview must be labelled as non-canonical runtime preview.",
            )
        )

    if output_binding.get("format") != "CLSYBND1":
        issues.append(
            _issue(
                "geometry_runtime_binding_result_binding_format_invalid",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime proposal binding must use CLSYBND1.",
            )
        )
    if (
        output_binding.get("runtimeUseAllowed") is not True
        or output_binding.get("accepted") is not True
    ):
        issues.append(
            _issue(
                "geometry_runtime_binding_result_binding_acceptance_invalid",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime proposal binding must be accepted for runtime preview only.",
            )
        )
    if output_binding_manifest.get("path") != "binding/proposal_binding_manifest.json":
        issues.append(
            _issue(
                "geometry_runtime_binding_result_binding_manifest_path_invalid",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime binding result must reference binding/proposal_binding_manifest.json.",
            )
        )
    for key in [
        "format",
        "algorithm",
        "recordCount",
        "sourceSimulationPath",
        "targetRenderPath",
        "simulationTopologyHash",
        "renderTopologyHash",
        "maximumReconstructionError",
        "rmsReconstructionError",
    ]:
        if output_binding_manifest.get(key) != proposal_binding_manifest.get(key):
            issues.append(
                _issue(
                    "geometry_runtime_binding_result_binding_manifest_mismatch",
                    "fatal",
                    "reports/geometry_runtime_binding_result.json",
                    f"Runtime binding manifest field {key} is stale.",
                )
            )

    if output_binding_path is not None:
        try:
            runtime_binding = read_binding(output_binding_path)
        except Exception as exc:
            issues.append(
                _issue(
                    "geometry_runtime_binding_result_binding_invalid",
                    "fatal",
                    "binding/proposal_sim_to_render.bin",
                    str(exc),
                )
            )
            runtime_binding = None
        if runtime_binding is not None:
            if runtime_binding.simulation_topology_hash != proposal_binding_manifest.get(
                "simulationTopologyHash"
            ):
                issues.append(
                    _issue(
                        "geometry_runtime_binding_result_binding_sim_topology_mismatch",
                        "fatal",
                        "binding/proposal_sim_to_render.bin",
                        "Proposal binding simulation topology hash is stale.",
                    )
                )
            if runtime_binding.render_topology_hash != proposal_binding_manifest.get(
                "renderTopologyHash"
            ):
                issues.append(
                    _issue(
                        "geometry_runtime_binding_result_binding_render_topology_mismatch",
                        "fatal",
                        "binding/proposal_sim_to_render.bin",
                        "Proposal binding render topology hash is stale.",
                    )
                )
            if len(runtime_binding.records) != int(
                proposal_binding_manifest.get("recordCount", -1)
            ):
                issues.append(
                    _issue(
                        "geometry_runtime_binding_result_binding_record_count_mismatch",
                        "fatal",
                        "binding/proposal_sim_to_render.bin",
                        "Proposal binding record count does not match its manifest.",
                    )
                )

    expected_render_hash = ""
    expected_binding_hash = ""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        expected_render_path = temp / "manual_runtime_retopology_preview.glb"
        expected_binding_path = temp / "proposal_sim_to_render.bin"
        try:
            expected_render_mesh, expected_binding_seeds = build_proposal_runtime_render_mesh(
                settled_mesh
            )
            expected_binding, expected_binding_manifest = build_proposal_runtime_binding(
                settled_simulation_mesh=settled_mesh,
                runtime_render_mesh=expected_render_mesh,
                render_binding_seeds=expected_binding_seeds,
                target_render_path="proposals/manual_runtime_retopology_preview.glb",
            )
            write_indexed_glb(
                expected_render_path,
                expected_render_mesh,
                "closy_proposal_runtime_retopology_preview_v1",
                (0.54, 0.70, 0.90, 1.0),
            )
            write_binding(expected_binding_path, expected_binding)
            expected_report = build_geometry_runtime_binding_result_report(
                garment_id=str(manifest.get("garmentId", "")),
                garment_class=str(manifest.get("garmentClass", "")),
                repair_result_report=repair_result,
                semantic_transfer_report=semantic_transfer,
                binding_candidate_report=binding_candidate,
                binding_validation_report=binding_validation,
                repair_asset_path=package_dir / "proposals" / "manual_repair_preview.glb",
                output_render_asset_path=expected_render_path,
                output_render_package_path="proposals/manual_runtime_retopology_preview.glb",
                output_binding_path=expected_binding_path,
                output_binding_package_path="binding/proposal_sim_to_render.bin",
                output_binding_manifest=expected_binding_manifest,
                output_binding_manifest_package_path="binding/proposal_binding_manifest.json",
                output_render_mesh=expected_render_mesh,
                settled_simulation_mesh=settled_mesh,
                settled_simulation_mesh_path="simulation/simulation_mesh.glb",
                constraints=constraints,
            )
            expected_render_hash = sha256_file(expected_render_path)
            expected_binding_hash = sha256_file(expected_binding_path)
        except Exception as exc:
            issues.append(
                _issue(
                    "geometry_runtime_binding_result_recompute_failed",
                    "fatal",
                    "reports/geometry_runtime_binding_result.json",
                    str(exc),
                )
            )
            return

    if proposal_binding_manifest != expected_binding_manifest:
        issues.append(
            _issue(
                "geometry_runtime_binding_result_proposal_binding_manifest_mismatch",
                "fatal",
                "binding/proposal_binding_manifest.json",
                "Proposal runtime binding manifest is stale.",
            )
        )
    for key in [
        "inputRepairAsset",
        "targetSettledSimulation",
        "outputRenderAsset",
        "outputBinding",
        "outputBindingManifest",
        "outputRenderMesh",
        "retopology",
        "seamContinuity",
        "checks",
        "executedOperations",
        "deferredOperations",
        "aggregate",
        "execution",
        "readiness",
        "quality",
    ]:
        if runtime_result.get(key) != expected_report.get(key):
            issues.append(
                _issue(
                    "geometry_runtime_binding_result_recompute_mismatch",
                    "fatal",
                    "reports/geometry_runtime_binding_result.json",
                    f"Runtime binding result field {key} is stale.",
                )
            )
    if output_render_asset.get("sourceAssetHash") != expected_render_hash:
        issues.append(
            _issue(
                "geometry_runtime_binding_result_render_asset_determinism_mismatch",
                "fatal",
                "proposals/manual_runtime_retopology_preview.glb",
                "Runtime retopology preview GLB does not match deterministic output.",
            )
        )
    if (
        output_render_asset_path is not None
        and sha256_file(output_render_asset_path) != expected_render_hash
    ):
        issues.append(
            _issue(
                "geometry_runtime_binding_result_render_asset_hash_mismatch",
                "fatal",
                "proposals/manual_runtime_retopology_preview.glb",
                "Runtime retopology preview GLB hash is stale.",
            )
        )
    if output_binding.get("sourceAssetHash") != expected_binding_hash:
        issues.append(
            _issue(
                "geometry_runtime_binding_result_binding_determinism_mismatch",
                "fatal",
                "binding/proposal_sim_to_render.bin",
                "Runtime proposal binding does not match deterministic output.",
            )
        )
    if (
        output_binding_path is not None
        and sha256_file(output_binding_path) != expected_binding_hash
    ):
        issues.append(
            _issue(
                "geometry_runtime_binding_result_binding_hash_mismatch",
                "fatal",
                "binding/proposal_sim_to_render.bin",
                "Runtime proposal binding hash is stale.",
            )
        )

    if (
        execution.get("runtimeBindingResultGenerated") is not True
        or execution.get("deformationReprojectionRun") is not True
        or execution.get("repairRun") is not True
        or execution.get("retopologyRun") is not True
        or execution.get("seamSplitRun") is not True
        or execution.get("componentStitchingRun") is not True
        or execution.get("normalContinuityValidationRun") is not True
        or execution.get("tangentContinuityValidationRun") is not True
        or execution.get("runtimeBindingWritten") is not True
        or execution.get("runtimeBindingAccepted") is not True
        or execution.get("cleanProposalRun") is not False
    ):
        issues.append(
            _issue(
                "geometry_runtime_binding_result_execution_state_invalid",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime binding result must claim only deterministic retopology and binding work.",
            )
        )
    if (
        readiness.get("status") != "runtime_binding_ready_clean_acceptance_pending"
        or readiness.get("acceptedForCleanProposal") is not False
        or readiness.get("acceptedForCanonical") is not False
        or readiness.get("acceptedForSimulation") is not True
        or readiness.get("acceptedForRuntimeRender") is not True
    ):
        issues.append(
            _issue(
                "geometry_runtime_binding_result_acceptance_invalid",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                (
                    "Runtime binding result may be accepted for simulation/runtime preview "
                    "only, not clean or canonical use."
                ),
            )
        )
    if quality.get("status") != "runtime_binding_pass_clean_rejected":
        issues.append(
            _issue(
                "geometry_runtime_binding_result_quality_status_invalid",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime binding quality must pass only with clean acceptance still rejected.",
            )
        )
    if (
        _int_or(aggregate.get("runtimeBindingRecordCount"), -1) != settled_mesh.triangle_count * 6
        or _float_or(aggregate.get("maxReconstructionError"), 1.0) > 1e-6
        or _float_or(aggregate.get("rmsReconstructionError"), 1.0) > 1e-6
        or aggregate.get("runtimeBindingAccepted") is not True
    ):
        issues.append(
            _issue(
                "geometry_runtime_binding_result_aggregate_invalid",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime binding aggregate must record exact reconstruction and acceptance.",
            )
        )
    if (
        policy.get("allowExternalApis") is not False
        or policy.get("allowTrainingUse") is not False
        or policy.get("containsUserImagery") is not False
        or policy.get("containsPersonalBodyData") is not False
        or policy.get("approvedDomain") != "avatar_and_garment_only"
    ):
        issues.append(
            _issue(
                "geometry_runtime_binding_result_policy_violation",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime binding result cannot permit external APIs, training use or user data.",
            )
        )
    caps = manifest.get("capabilities", {})
    if isinstance(caps, dict) and caps.get("geometryRuntimeBindingResultAvailable") is not True:
        issues.append(
            _issue(
                "geometry_runtime_binding_result_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest capability geometryRuntimeBindingResultAvailable must be true.",
            )
        )
    if _contains_nonfinite(runtime_result):
        issues.append(
            _issue(
                "geometry_runtime_binding_result_nonfinite_numeric_value",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime binding result must not contain NaN or Infinity.",
            )
        )


def _validate_geometry_material_uv_transfer(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    runtime_result = _read_required_json(
        package_dir, "reports/geometry_runtime_binding_result.json", issues
    )
    semantic_transfer = _read_required_json(
        package_dir, "reports/geometry_semantic_transfer.json", issues
    )
    texture_identity = _read_required_json(package_dir, "textures/texture_identity.json", issues)
    render_materials = _read_required_json(package_dir, "render/materials.json", issues)
    simulation_manifest = _read_required_json(package_dir, "simulation/mesh_manifest.json", issues)
    material_transfer = _read_required_json(
        package_dir, "reports/geometry_material_uv_transfer.json", issues
    )
    if (
        runtime_result is None
        or semantic_transfer is None
        or texture_identity is None
        or render_materials is None
        or simulation_manifest is None
        or material_transfer is None
    ):
        return

    if material_transfer.get("garmentId") != manifest.get("garmentId"):
        issues.append(
            _issue(
                "geometry_material_uv_transfer_garment_mismatch",
                "fatal",
                "reports/geometry_material_uv_transfer.json",
                "Material/UV transfer report must reference the package garment ID.",
            )
        )
    if material_transfer.get("garmentClass") != manifest.get("garmentClass"):
        issues.append(
            _issue(
                "geometry_material_uv_transfer_class_mismatch",
                "fatal",
                "reports/geometry_material_uv_transfer.json",
                "Material/UV transfer report must reference the package garment class.",
            )
        )

    expected_sources = [
        (
            "sourceGeometryRuntimeBindingResultId",
            runtime_result.get("reportId"),
            "geometry_material_uv_transfer_runtime_source_mismatch",
        ),
        (
            "sourceGeometrySemanticTransferId",
            semantic_transfer.get("reportId"),
            "geometry_material_uv_transfer_semantic_source_mismatch",
        ),
        (
            "sourceTextureIdentityId",
            texture_identity.get("textureIdentityId"),
            "geometry_material_uv_transfer_texture_source_mismatch",
        ),
    ]
    for field, expected_value, code in expected_sources:
        if material_transfer.get(field) != expected_value:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "reports/geometry_material_uv_transfer.json",
                    f"Material/UV transfer {field} must match its source artifact.",
                )
            )

    expected_hashes = [
        (
            "sourceGeometryRuntimeBindingResultHash",
            _nested_string(runtime_result, ["integrity", "geometryRuntimeBindingResultHash"], ""),
            "geometry_material_uv_transfer_runtime_hash_mismatch",
        ),
        (
            "sourceGeometrySemanticTransferHash",
            _nested_string(semantic_transfer, ["integrity", "geometrySemanticTransferHash"], ""),
            "geometry_material_uv_transfer_semantic_hash_mismatch",
        ),
        (
            "sourceTextureIdentityHash",
            _nested_string(texture_identity, ["integrity", "textureIdentityHash"], ""),
            "geometry_material_uv_transfer_texture_hash_mismatch",
        ),
        (
            "sourceRenderMaterialsHash",
            _json_hash(render_materials),
            "geometry_material_uv_transfer_render_materials_hash_mismatch",
        ),
    ]
    for field, expected_hash, code in expected_hashes:
        if material_transfer.get(field) != expected_hash:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "reports/geometry_material_uv_transfer.json",
                    f"Material/UV transfer {field} must match its source artifact.",
                )
            )

    if _nested_string(material_transfer, ["integrity", "geometryMaterialUvTransferHash"], "") != (
        hash_geometry_material_uv_transfer(material_transfer)
    ):
        issues.append(
            _issue(
                "geometry_material_uv_transfer_hash_mismatch",
                "fatal",
                "reports/geometry_material_uv_transfer.json",
                "Material/UV transfer report hash must match its canonical payload.",
            )
        )

    try:
        settled_mesh = _meshset_from_manifest(simulation_manifest)
        runtime_render_mesh, _binding_seeds = build_proposal_runtime_render_mesh(settled_mesh)
    except Exception as exc:
        issues.append(
            _issue(
                "geometry_material_uv_transfer_mesh_rebuild_failed",
                "fatal",
                "reports/geometry_material_uv_transfer.json",
                str(exc),
            )
        )
        return

    if material_transfer.get("sourceRuntimeRenderMeshTopologyHash") != topology_hash(
        runtime_render_mesh
    ):
        issues.append(
            _issue(
                "geometry_material_uv_transfer_runtime_topology_hash_mismatch",
                "fatal",
                "reports/geometry_material_uv_transfer.json",
                "Material/UV transfer runtime render topology hash is stale.",
            )
        )
    if material_transfer.get("sourceRuntimeRenderMeshContentHash") != geometry_content_hash(
        runtime_render_mesh
    ):
        issues.append(
            _issue(
                "geometry_material_uv_transfer_runtime_content_hash_mismatch",
                "fatal",
                "reports/geometry_material_uv_transfer.json",
                "Material/UV transfer runtime render content hash is stale.",
            )
        )

    try:
        expected_report = build_geometry_material_uv_transfer_report(
            garment_id=str(manifest.get("garmentId", "")),
            garment_class=str(manifest.get("garmentClass", "")),
            runtime_binding_result_report=runtime_result,
            semantic_transfer_report=semantic_transfer,
            texture_identity_report=texture_identity,
            render_materials=render_materials,
            runtime_render_mesh=runtime_render_mesh,
        )
    except Exception as exc:
        issues.append(
            _issue(
                "geometry_material_uv_transfer_recompute_failed",
                "fatal",
                "reports/geometry_material_uv_transfer.json",
                str(exc),
            )
        )
        return

    for key in [
        "candidate",
        "uvTransfer",
        "materialTransfer",
        "pbrTransfer",
        "aggregate",
        "execution",
        "readiness",
        "quality",
        "policy",
    ]:
        if material_transfer.get(key) != expected_report.get(key):
            issues.append(
                _issue(
                    "geometry_material_uv_transfer_recompute_mismatch",
                    "fatal",
                    "reports/geometry_material_uv_transfer.json",
                    f"Material/UV transfer field {key} is stale.",
                )
            )

    candidate = material_transfer.get("candidate", {})
    aggregate = material_transfer.get("aggregate", {})
    execution = material_transfer.get("execution", {})
    readiness = material_transfer.get("readiness", {})
    quality = material_transfer.get("quality", {})
    policy = material_transfer.get("policy", {})
    for name, block in [
        ("candidate", candidate),
        ("aggregate", aggregate),
        ("execution", execution),
        ("readiness", readiness),
        ("quality", quality),
        ("policy", policy),
    ]:
        if not isinstance(block, dict):
            issues.append(
                _issue(
                    "geometry_material_uv_transfer_block_invalid",
                    "fatal",
                    "reports/geometry_material_uv_transfer.json",
                    f"Material/UV transfer {name} block must be an object.",
                )
            )
            return

    if (
        execution.get("materialUvTransferReportGenerated") is not True
        or execution.get("uvTransferRun") is not True
        or execution.get("materialTransferRun") is not True
        or execution.get("sourceTextureProjectionRun")
        != texture_identity.get("textureProjectionRun")
        or execution.get("visualFidelityReviewRun") is not False
        or execution.get("singleShellWeldProofRun") is not False
    ):
        issues.append(
            _issue(
                "geometry_material_uv_transfer_execution_state_invalid",
                "fatal",
                "reports/geometry_material_uv_transfer.json",
                (
                    "Material/UV transfer may claim authored PBR and UV transfer only; "
                    "visual fidelity and weld proof must remain separate."
                ),
            )
        )
    if (
        readiness.get("status") != "material_uv_transfer_completed_fidelity_weld_pending"
        or readiness.get("acceptedForMaterialPreview") is not True
        or readiness.get("acceptedForCleanProposal") is not False
        or readiness.get("acceptedForCanonical") is not False
        or readiness.get("acceptedForRuntimeRender")
        != runtime_result.get("readiness", {}).get("acceptedForRuntimeRender")
    ):
        issues.append(
            _issue(
                "geometry_material_uv_transfer_acceptance_invalid",
                "fatal",
                "reports/geometry_material_uv_transfer.json",
                (
                    "Material/UV transfer can accept material preview evidence but not clean "
                    "or canonical geometry."
                ),
            )
        )
    if quality.get("status") != "pass_runtime_material_preview_clean_rejected":
        issues.append(
            _issue(
                "geometry_material_uv_transfer_quality_status_invalid",
                "fatal",
                "reports/geometry_material_uv_transfer.json",
                (
                    "Material/UV transfer quality must pass only for runtime preview "
                    "material evidence."
                ),
            )
        )
    if (
        aggregate.get("acceptedForMaterialPreview") is not True
        or aggregate.get("acceptedForCleanProposal") is not False
        or aggregate.get("acceptedForCanonical") is not False
        or _int_or(aggregate.get("missingUvCount"), -1) != 0
        or _int_or(aggregate.get("missingMaterialCount"), -1) != 0
        or _int_or(aggregate.get("transferredMaterialCount"), 0) <= 0
    ):
        issues.append(
            _issue(
                "geometry_material_uv_transfer_aggregate_invalid",
                "fatal",
                "reports/geometry_material_uv_transfer.json",
                "Material/UV transfer aggregate must record complete preview material evidence.",
            )
        )
    if (
        policy.get("allowExternalApis") is not False
        or policy.get("allowTrainingUse") is not False
        or policy.get("containsUserImagery") is not False
        or policy.get("containsPersonalBodyData") is not False
        or policy.get("approvedDomain") != "avatar_and_garment_only"
    ):
        issues.append(
            _issue(
                "geometry_material_uv_transfer_policy_violation",
                "fatal",
                "reports/geometry_material_uv_transfer.json",
                "Material/UV transfer cannot permit external APIs, training use or user data.",
            )
        )
    caps = manifest.get("capabilities", {})
    if isinstance(caps, dict) and caps.get("geometryMaterialUvTransferAvailable") is not True:
        issues.append(
            _issue(
                "geometry_material_uv_transfer_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest capability geometryMaterialUvTransferAvailable must be true.",
            )
        )
    if _contains_nonfinite(material_transfer):
        issues.append(
            _issue(
                "geometry_material_uv_transfer_nonfinite_numeric_value",
                "fatal",
                "reports/geometry_material_uv_transfer.json",
                "Material/UV transfer report must not contain NaN or Infinity.",
            )
        )


def _validate_geometry_stitched_shell(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    simulation_manifest = _read_required_json(package_dir, "simulation/mesh_manifest.json", issues)
    constraints = _read_required_json(package_dir, "simulation/constraints.json", issues)
    report = _read_required_json(package_dir, "reports/geometry_stitched_shell.json", issues)
    analysis = _read_required_json(
        package_dir, "stitch/logical_stitched_analysis_shell.json", issues
    )
    if simulation_manifest is None or constraints is None or report is None or analysis is None:
        return

    if report.get("garmentId") != manifest.get("garmentId"):
        issues.append(
            _issue(
                "geometry_stitched_shell_garment_mismatch",
                "fatal",
                "reports/geometry_stitched_shell.json",
                "Stitched shell report must reference the package garment ID.",
            )
        )
    if report.get("garmentClass") != manifest.get("garmentClass"):
        issues.append(
            _issue(
                "geometry_stitched_shell_class_mismatch",
                "fatal",
                "reports/geometry_stitched_shell.json",
                "Stitched shell report must reference the package garment class.",
            )
        )

    try:
        settled_mesh = _meshset_from_manifest(simulation_manifest)
        expected_report, expected_analysis, expected_mesh = build_stitched_shell_assets(
            garment_id=str(manifest.get("garmentId", "")),
            garment_class=str(manifest.get("garmentClass", "")),
            source_simulation_mesh=settled_mesh,
            constraints=constraints,
            analysis_asset_path="stitch/logical_stitched_analysis_shell.json",
            render_asset_path="render/stitched_shell.glb",
        )
    except Exception as exc:
        issues.append(
            _issue(
                "geometry_stitched_shell_recompute_failed",
                "fatal",
                "reports/geometry_stitched_shell.json",
                str(exc),
            )
        )
        return
    if report.get("sourceSimulationMeshTopologyHash") != topology_hash(settled_mesh):
        issues.append(
            _issue(
                "geometry_stitched_shell_source_topology_hash_mismatch",
                "fatal",
                "reports/geometry_stitched_shell.json",
                "Stitched shell source topology hash is stale.",
            )
        )
    if report.get("sourceSimulationMeshContentHash") != geometry_content_hash(settled_mesh):
        issues.append(
            _issue(
                "geometry_stitched_shell_source_content_hash_mismatch",
                "fatal",
                "reports/geometry_stitched_shell.json",
                "Stitched shell source content hash is stale.",
            )
        )
    if _nested_string(report, ["integrity", "geometryStitchedShellHash"], "") != (
        hash_geometry_stitched_shell_report(report)
    ):
        issues.append(
            _issue(
                "geometry_stitched_shell_hash_mismatch",
                "fatal",
                "reports/geometry_stitched_shell.json",
                "Stitched shell report hash must match its canonical payload.",
            )
        )
    if _nested_string(analysis, ["integrity", "stitchedAnalysisShellHash"], "") != (
        hash_stitched_analysis_shell(analysis)
    ):
        issues.append(
            _issue(
                "stitched_analysis_shell_hash_mismatch",
                "fatal",
                "stitch/logical_stitched_analysis_shell.json",
                "Stitched analysis shell hash must match its canonical payload.",
            )
        )

    for key in [
        "analysisAsset",
        "renderAsset",
        "execution",
        "topologyAudit",
        "readiness",
        "quality",
        "policy",
    ]:
        if report.get(key) != expected_report.get(key):
            issues.append(
                _issue(
                    "geometry_stitched_shell_recompute_mismatch",
                    "fatal",
                    "reports/geometry_stitched_shell.json",
                    f"Stitched shell field {key} is stale.",
                )
            )
    for key in [
        "sourceSimulationMeshTopologyHash",
        "sourceSimulationMeshContentHash",
        "logicalShellTopologyHash",
        "logicalShellContentHash",
        "logicalShell",
        "sourceVertexMap",
        "executedOperations",
        "openingProof",
        "topologyAudit",
        "readiness",
        "policy",
    ]:
        if analysis.get(key) != expected_analysis.get(key):
            issues.append(
                _issue(
                    "stitched_analysis_shell_recompute_mismatch",
                    "fatal",
                    "stitch/logical_stitched_analysis_shell.json",
                    f"Stitched analysis shell field {key} is stale.",
                )
            )

    if report.get("analysisAsset", {}).get("payloadHash") != _nested_string(
        analysis, ["integrity", "stitchedAnalysisShellHash"], ""
    ):
        issues.append(
            _issue(
                "geometry_stitched_shell_analysis_hash_mismatch",
                "fatal",
                "reports/geometry_stitched_shell.json",
                "Stitched shell report must reference the analysis asset hash.",
            )
        )
    render_asset = report.get("renderAsset", {})
    execution = report.get("execution", {})
    if (
        execution.get("analysisAssetWritten") is not False
        or execution.get("renderAssetWritten") is not False
        or execution.get("analysisAssetWriteStatus") != "declared_package_writer_required"
        or execution.get("renderAssetWriteStatus") != "declared_package_writer_required"
    ):
        issues.append(
            _issue(
                "geometry_stitched_shell_builder_write_claim_invalid",
                "fatal",
                "reports/geometry_stitched_shell.json",
                "The pure stitched-shell builder must not claim package files were written.",
            )
        )
    if render_asset.get("path") != "render/stitched_shell.glb":
        issues.append(
            _issue(
                "geometry_stitched_shell_render_path_invalid",
                "fatal",
                "reports/geometry_stitched_shell.json",
                "Stitched render shell path must be render/stitched_shell.glb.",
            )
        )
    writer_evidence = report.get("packageWriterEvidence", {})
    analysis_asset_path = package_dir / "stitch" / "logical_stitched_analysis_shell.json"
    render_asset_path = package_dir / "render" / "stitched_shell.glb"
    expected_writer_evidence = {
        "status": "written",
        "analysisAssetWritten": analysis_asset_path.exists(),
        "renderAssetWritten": render_asset_path.exists(),
        "analysisAssetPath": "stitch/logical_stitched_analysis_shell.json",
        "renderAssetPath": "render/stitched_shell.glb",
        "analysisAssetSha256": sha256_file(analysis_asset_path)
        if analysis_asset_path.exists()
        else None,
        "renderAssetSha256": sha256_file(render_asset_path) if render_asset_path.exists() else None,
        "analysisAssetByteSize": analysis_asset_path.stat().st_size
        if analysis_asset_path.exists()
        else None,
        "renderAssetByteSize": render_asset_path.stat().st_size
        if render_asset_path.exists()
        else None,
    }
    if writer_evidence != expected_writer_evidence:
        issues.append(
            _issue(
                "geometry_stitched_shell_package_writer_evidence_mismatch",
                "fatal",
                "reports/geometry_stitched_shell.json",
                (
                    "Stitched shell package-writer evidence must match the written "
                    "analysis and GLB files."
                ),
            )
        )
    if render_asset.get("topologyHash") != topology_hash(expected_mesh):
        issues.append(
            _issue(
                "geometry_stitched_shell_render_topology_hash_mismatch",
                "fatal",
                "reports/geometry_stitched_shell.json",
                "Stitched render shell topology hash is stale.",
            )
        )
    if render_asset.get("contentHash") != geometry_content_hash(expected_mesh):
        issues.append(
            _issue(
                "geometry_stitched_shell_render_content_hash_mismatch",
                "fatal",
                "reports/geometry_stitched_shell.json",
                "Stitched render shell content hash is stale.",
            )
        )
    topology_audit = report.get("topologyAudit", {})
    seam_coverage = topology_audit.get("seamSpanCoverage", {})
    if (
        not isinstance(seam_coverage, dict)
        or seam_coverage.get("requiredOperationCount")
        != topology_audit.get("sourceConstraintCount")
        or seam_coverage.get("executedRequiredOperationCount")
        != topology_audit.get("executedOperationCount")
        or seam_coverage.get("coverageRatio") != 1.0
    ):
        issues.append(
            _issue(
                "geometry_stitched_shell_seam_coverage_invalid",
                "fatal",
                "reports/geometry_stitched_shell.json",
                (
                    "Stitched shell seam coverage must expose exact "
                    "required/executed operation counts."
                ),
            )
        )
    ordered_correspondence = topology_audit.get("orderedSeamCorrespondenceAudit", {})
    if (
        not isinstance(ordered_correspondence, dict)
        or topology_audit.get("orderedSeamCorrespondenceStatus")
        != ordered_correspondence.get("status")
        or ordered_correspondence.get("sourceConstraintCount")
        != topology_audit.get("sourceConstraintCount")
        or ordered_correspondence.get("executedOperationCount")
        != topology_audit.get("executedOperationCount")
        or ordered_correspondence.get("duplicatedOperationIdCount")
        != seam_coverage.get("duplicateExecutedOperationCount")
        or ordered_correspondence.get("unmatchedCorrespondenceCount")
        != len(seam_coverage.get("missingRequiredOperationIds", []))
        or ordered_correspondence.get("status") not in {"pass", "fail"}
        or not isinstance(ordered_correspondence.get("distanceToleranceMeters"), int | float)
        or not isinstance(ordered_correspondence.get("preStitchDistanceDistributionMeters"), dict)
        or not isinstance(ordered_correspondence.get("postStitchResidualDistributionMeters"), dict)
        or (
            ordered_correspondence.get("status") == "pass"
            and (
                ordered_correspondence.get("failureReasons") != []
                or ordered_correspondence.get("reusedBoundaryVertexCount") != 0
                or ordered_correspondence.get("reusedBoundarySpanCount") != 0
                or ordered_correspondence.get("oversizedPreStitchCorrespondenceCount") != 0
                or ordered_correspondence.get("multiSpanFanoutSeamIds") != []
            )
        )
        or (
            ordered_correspondence.get("status") == "fail"
            and not ordered_correspondence.get("failureReasons")
        )
    ):
        issues.append(
            _issue(
                "geometry_stitched_shell_ordered_correspondence_invalid",
                "fatal",
                "reports/geometry_stitched_shell.json",
                (
                    "BP-46 stitched shell ordered seam correspondence must expose "
                    "truthful executed/missing/duplicate counts and fail closed when "
                    "spans are reused without partitioning."
                ),
            )
        )
    binding_evidence = topology_audit.get("bindingEvidence", {})
    if (
        not isinstance(binding_evidence, dict)
        or topology_audit.get("bindingCoverage") != binding_evidence.get("coverageRatio")
        or binding_evidence.get("requiredRenderVertexCount") != topology_audit.get("vertexCount")
        or binding_evidence.get("bindingStatus") != "pass"
        or binding_evidence.get("bindingMode") != "logical_source_vertex_centroid_map"
        or binding_evidence.get("bindingFormat") != "logical_source_vertex_centroid_map_v1"
        or binding_evidence.get("bindingAssetPath")
        != "stitch/logical_stitched_analysis_shell.json#sourceVertexMap"
        or binding_evidence.get("boundRenderVertexCount") != topology_audit.get("vertexCount")
        or topology_audit.get("bindingCoverage") != 1.0
        or binding_evidence.get("missingRenderVertexIds") != []
        or binding_evidence.get("duplicateRenderVertexIds") != []
        or binding_evidence.get("invalidBindingRecordIds") != []
        or binding_evidence.get("bindingRecordCount") != topology_audit.get("vertexCount")
        or binding_evidence.get("topologyHash") != topology_hash(expected_mesh)
        or binding_evidence.get("contentHash") != geometry_content_hash(expected_mesh)
        or topology_audit.get("bindingReconstructionStatus") != "pass"
        or binding_evidence.get("reconstructionStatus") != "pass"
        or topology_audit.get("bindingReconstructionErrorMeters")
        != binding_evidence.get("maxReconstructionErrorMeters")
        or not isinstance(binding_evidence.get("maxReconstructionErrorMeters"), int | float)
        or not isinstance(binding_evidence.get("rmsReconstructionErrorMeters"), int | float)
        or not isinstance(binding_evidence.get("reconstructionToleranceMeters"), int | float)
        or float(binding_evidence.get("maxReconstructionErrorMeters", 1.0))
        > float(binding_evidence.get("reconstructionToleranceMeters", 0.0))
        or binding_evidence.get("failureReasons") != []
    ):
        issues.append(
            _issue(
                "geometry_stitched_shell_binding_coverage_invalid",
                "fatal",
                "reports/geometry_stitched_shell.json",
                (
                    "BP-46 stitched shell binding evidence must execute and expose "
                    "complete logical source-vertex reconstruction coverage."
                ),
            )
        )
    provenance = topology_audit.get("uvMaterialPanelProvenance", {})
    if (
        not isinstance(provenance, dict)
        or topology_audit.get("uvMaterialPanelProvenanceCoverage")
        != provenance.get("coverageRatio")
        or provenance.get("requiredOutputVertexCount") != topology_audit.get("vertexCount")
        or provenance.get("coveredOutputVertexCount") != topology_audit.get("vertexCount")
    ):
        issues.append(
            _issue(
                "geometry_stitched_shell_provenance_coverage_invalid",
                "fatal",
                "reports/geometry_stitched_shell.json",
                (
                    "Stitched shell provenance coverage must expose output-vertex "
                    "numerator and denominator."
                ),
            )
        )
    opening_proof = analysis.get("openingProof", {})
    expected_opening_ids = (
        opening_proof.get("expectedOpeningIds", []) if isinstance(opening_proof, dict) else []
    )
    source_opening_provenance = (
        opening_proof.get("sourceOpeningEdgeProvenance", {})
        if isinstance(opening_proof, dict)
        else {}
    )
    source_opening_provenance_valid = (
        isinstance(source_opening_provenance, dict)
        and opening_proof.get("panelEdgeProvenanceStatus") == "pass"
        and source_opening_provenance.get("status") == "pass"
        and source_opening_provenance.get("recordedOpeningCount") == len(expected_opening_ids)
        and source_opening_provenance.get("missingOpeningIds") == []
        and source_opening_provenance.get("missingBoundaryEdges") == []
        and source_opening_provenance.get("missingLogicalVertices") == []
        and source_opening_provenance.get("unexpectedSeamOwnedOpeningEdges") == []
        and source_opening_provenance.get("unexpectedOpeningBoundaryEdges") == []
    )
    semantic_opening_audit = topology_audit.get("semanticOpeningAudit", {})
    candidate_mappings = (
        opening_proof.get("candidateOpeningMappings", []) if isinstance(opening_proof, dict) else []
    )
    opening_proof_valid = (
        isinstance(opening_proof, dict)
        and isinstance(semantic_opening_audit, dict)
        and opening_proof.get("status") == "pass"
        and opening_proof.get("semanticOpeningAssignmentStatus") == "pass"
        and semantic_opening_audit.get("status") == "pass"
        and opening_proof.get("expectedOpeningIds") == expected_opening_ids
        and opening_proof.get("topologicalBoundaryComponentCount")
        == topology_audit.get("boundaryLoopCount")
        and opening_proof.get("simpleBoundaryCycleCount")
        == topology_audit.get("simpleBoundaryCycleCount")
        and opening_proof.get("boundaryBranchVertexCount")
        == topology_audit.get("boundaryBranchVertexCount")
        and opening_proof.get("missingExpectedOpeningCount") == 0
        and opening_proof.get("provenOpeningCount") == len(expected_opening_ids)
        and opening_proof.get("provenOpeningIds") == expected_opening_ids
        and opening_proof.get("missingExpectedOpeningIds") == []
        and isinstance(candidate_mappings, list)
        and len(candidate_mappings) == len(expected_opening_ids)
        and all(
            isinstance(mapping, dict)
            and mapping.get("openingId") in expected_opening_ids
            and mapping.get("assignmentStatus") == "pass"
            and mapping.get("orderedLoopVertexIds")
            and mapping.get("orderedLoopEdgeIds")
            and mapping.get("contributingSourcePanelEdgeIds")
            for mapping in candidate_mappings
        )
        and opening_proof.get("failureReasons") == []
        and source_opening_provenance_valid
    )
    if not opening_proof_valid:
        issues.append(
            _issue(
                "stitched_analysis_shell_opening_proof_invalid",
                "fatal",
                "stitch/logical_stitched_analysis_shell.json",
                "Opening proof must match recomputed semantic boundary-loop evidence.",
            )
        )
    if report.get("readiness", {}).get("meshStitchOrWeldProven") is True and not (
        topology_audit.get("finiteMesh") is True
        and topology_audit.get("logicalShellCount") == 1
        and topology_audit.get("seamSpanCoverage", {}).get("coverageRatio") == 1.0
        and topology_audit.get("seamSpanCoverage", {}).get("rejectedRequiredOperationCount") == 0
        and topology_audit.get("seamSpanCoverage", {}).get("duplicateExecutedOperationCount") == 0
        and topology_audit.get("orderedSeamCorrespondenceStatus") == "pass"
        and topology_audit.get("nonManifoldEdgeCount") == 0
        and topology_audit.get("nonManifoldVertexCount") == 0
        and topology_audit.get("duplicateFaceCount") == 0
        and topology_audit.get("degenerateTriangleCount") == 0
        and topology_audit.get("surfaceTopologyStatus") == "pass"
        and topology_audit.get("eulerCharacteristic") == -2
        and topology_audit.get("genus") == 0
        and topology_audit.get("isolatedVertexCount") == 0
        and topology_audit.get("zeroLengthEdgeCount") == 0
        and topology_audit.get("smallTriangleCount") == 0
        and topology_audit.get("vertexLinkStatus") == "pass"
        and topology_audit.get("unexpectedBoundaryLoopCount") == 0
        and topology_audit.get("boundaryLoopCount") == topology_audit.get("expectedOpeningCount")
        and topology_audit.get("simpleBoundaryCycleCount")
        == topology_audit.get("expectedOpeningCount")
        and topology_audit.get("boundaryBranchVertexCount") == 0
        and topology_audit.get("missingExpectedOpeningCount") == 0
        and topology_audit.get("tJunctionCheckStatus") == "pass"
        and topology_audit.get("inconsistentWindingCheckStatus") == "pass"
        and topology_audit.get("normalInversionCheckStatus") == "pass"
        and topology_audit.get("selfIntersectionCheckStatus") == "pass"
        and topology_audit.get("hiddenInternalComponentCheckStatus") == "pass"
        and topology_audit.get("uvMaterialPanelProvenanceCoverage") == 1.0
        and topology_audit.get("bindingCoverage") == 1.0
        and topology_audit.get("bindingReconstructionStatus") == "pass"
    ):
        issues.append(
            _issue(
                "geometry_stitched_shell_proof_invalid",
                "fatal",
                "reports/geometry_stitched_shell.json",
                "Stitched shell cannot be proven while topology or self-intersection gates fail.",
            )
        )
    caps = manifest.get("capabilities", {})
    if isinstance(caps, dict) and caps.get("geometryStitchedShellAvailable") is not True:
        issues.append(
            _issue(
                "geometry_stitched_shell_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest capability geometryStitchedShellAvailable must be true.",
            )
        )
    if _contains_nonfinite(report):
        issues.append(
            _issue(
                "geometry_stitched_shell_nonfinite_numeric_value",
                "fatal",
                "reports/geometry_stitched_shell.json",
                "Stitched shell report must not contain NaN or Infinity.",
            )
        )
    if _contains_nonfinite(analysis):
        issues.append(
            _issue(
                "stitched_analysis_shell_nonfinite_numeric_value",
                "fatal",
                "stitch/logical_stitched_analysis_shell.json",
                "Stitched analysis shell must not contain NaN or Infinity.",
            )
        )


def _validate_geometry_visual_shell_review(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    runtime_result = _read_required_json(
        package_dir, "reports/geometry_runtime_binding_result.json", issues
    )
    semantic_transfer = _read_required_json(
        package_dir, "reports/geometry_semantic_transfer.json", issues
    )
    material_transfer = _read_required_json(
        package_dir, "reports/geometry_material_uv_transfer.json", issues
    )
    simulation_manifest = _read_required_json(package_dir, "simulation/mesh_manifest.json", issues)
    constraints = _read_required_json(package_dir, "simulation/constraints.json", issues)
    stitched_shell = _read_required_json(
        package_dir, "reports/geometry_stitched_shell.json", issues
    )
    visual_shell = _read_required_json(
        package_dir, "reports/geometry_visual_shell_review.json", issues
    )
    if (
        runtime_result is None
        or semantic_transfer is None
        or material_transfer is None
        or simulation_manifest is None
        or constraints is None
        or stitched_shell is None
        or visual_shell is None
    ):
        return

    if visual_shell.get("garmentId") != manifest.get("garmentId"):
        issues.append(
            _issue(
                "geometry_visual_shell_review_garment_mismatch",
                "fatal",
                "reports/geometry_visual_shell_review.json",
                "Visual/shell review must reference the package garment ID.",
            )
        )
    if visual_shell.get("garmentClass") != manifest.get("garmentClass"):
        issues.append(
            _issue(
                "geometry_visual_shell_review_class_mismatch",
                "fatal",
                "reports/geometry_visual_shell_review.json",
                "Visual/shell review must reference the package garment class.",
            )
        )

    expected_sources = [
        (
            "sourceGeometryRuntimeBindingResultId",
            runtime_result.get("reportId"),
            "geometry_visual_shell_review_runtime_source_mismatch",
        ),
        (
            "sourceGeometrySemanticTransferId",
            semantic_transfer.get("reportId"),
            "geometry_visual_shell_review_semantic_source_mismatch",
        ),
        (
            "sourceGeometryMaterialUvTransferId",
            material_transfer.get("reportId"),
            "geometry_visual_shell_review_material_uv_source_mismatch",
        ),
    ]
    for field, expected_value, code in expected_sources:
        if visual_shell.get(field) != expected_value:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "reports/geometry_visual_shell_review.json",
                    f"Visual/shell review {field} must match its source artifact.",
                )
            )

    expected_hashes = [
        (
            "sourceGeometryRuntimeBindingResultHash",
            _nested_string(runtime_result, ["integrity", "geometryRuntimeBindingResultHash"], ""),
            "geometry_visual_shell_review_runtime_hash_mismatch",
        ),
        (
            "sourceGeometrySemanticTransferHash",
            _nested_string(semantic_transfer, ["integrity", "geometrySemanticTransferHash"], ""),
            "geometry_visual_shell_review_semantic_hash_mismatch",
        ),
        (
            "sourceGeometryMaterialUvTransferHash",
            _nested_string(
                material_transfer,
                ["integrity", "geometryMaterialUvTransferHash"],
                "",
            ),
            "geometry_visual_shell_review_material_uv_hash_mismatch",
        ),
    ]
    for field, expected_hash, code in expected_hashes:
        if visual_shell.get(field) != expected_hash:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "reports/geometry_visual_shell_review.json",
                    f"Visual/shell review {field} must match its source artifact.",
                )
            )

    if _nested_string(visual_shell, ["integrity", "geometryVisualShellReviewHash"], "") != (
        hash_geometry_visual_shell_review(visual_shell)
    ):
        issues.append(
            _issue(
                "geometry_visual_shell_review_hash_mismatch",
                "fatal",
                "reports/geometry_visual_shell_review.json",
                "Visual/shell review hash must match its canonical payload.",
            )
        )

    try:
        settled_mesh = _meshset_from_manifest(simulation_manifest)
        runtime_render_mesh, _binding_seeds = build_proposal_runtime_render_mesh(settled_mesh)
    except Exception as exc:
        issues.append(
            _issue(
                "geometry_visual_shell_review_mesh_rebuild_failed",
                "fatal",
                "reports/geometry_visual_shell_review.json",
                str(exc),
            )
        )
        return

    if visual_shell.get("sourceRuntimeRenderMeshTopologyHash") != topology_hash(
        runtime_render_mesh
    ):
        issues.append(
            _issue(
                "geometry_visual_shell_review_runtime_topology_hash_mismatch",
                "fatal",
                "reports/geometry_visual_shell_review.json",
                "Visual/shell review runtime render topology hash is stale.",
            )
        )
    if visual_shell.get("sourceRuntimeRenderMeshContentHash") != geometry_content_hash(
        runtime_render_mesh
    ):
        issues.append(
            _issue(
                "geometry_visual_shell_review_runtime_content_hash_mismatch",
                "fatal",
                "reports/geometry_visual_shell_review.json",
                "Visual/shell review runtime render content hash is stale.",
            )
        )

    try:
        expected_report = build_geometry_visual_shell_review_report(
            garment_id=str(manifest.get("garmentId", "")),
            garment_class=str(manifest.get("garmentClass", "")),
            runtime_binding_result_report=runtime_result,
            semantic_transfer_report=semantic_transfer,
            material_uv_transfer_report=material_transfer,
            runtime_render_mesh=runtime_render_mesh,
            reference_simulation_mesh=settled_mesh,
            constraints=constraints,
            stitched_shell_report=stitched_shell,
        )
    except Exception as exc:
        issues.append(
            _issue(
                "geometry_visual_shell_review_recompute_failed",
                "fatal",
                "reports/geometry_visual_shell_review.json",
                str(exc),
            )
        )
        return

    for key in [
        "candidate",
        "representationEvidence",
        "appearanceEvidence",
        "visualFidelity",
        "shellProof",
        "aggregate",
        "execution",
        "readiness",
        "quality",
        "policy",
    ]:
        if visual_shell.get(key) != expected_report.get(key):
            issues.append(
                _issue(
                    "geometry_visual_shell_review_recompute_mismatch",
                    "fatal",
                    "reports/geometry_visual_shell_review.json",
                    f"Visual/shell review field {key} is stale.",
                )
            )

    aggregate = visual_shell.get("aggregate", {})
    execution = visual_shell.get("execution", {})
    readiness = visual_shell.get("readiness", {})
    quality = visual_shell.get("quality", {})
    policy = visual_shell.get("policy", {})
    stitched_execution_run = bool(
        stitched_shell.get("execution", {}).get("meshStitchOrWeldExecutionRun") is True
    )
    stitched_proven = bool(
        stitched_shell.get("readiness", {}).get("meshStitchOrWeldProven") is True
    )
    for name, block in [
        ("aggregate", aggregate),
        ("execution", execution),
        ("readiness", readiness),
        ("quality", quality),
        ("policy", policy),
        ("representationEvidence", visual_shell.get("representationEvidence", {})),
        ("appearanceEvidence", visual_shell.get("appearanceEvidence", {})),
        ("shellProof", visual_shell.get("shellProof", {})),
    ]:
        if not isinstance(block, dict):
            issues.append(
                _issue(
                    "geometry_visual_shell_review_block_invalid",
                    "fatal",
                    "reports/geometry_visual_shell_review.json",
                    f"Visual/shell review {name} block must be an object.",
                )
            )
            return

    if (
        execution.get("geometryVisualShellReviewGenerated") is not True
        or execution.get("deterministicPreviewProxyReviewRun") is not True
        or execution.get("representationSilhouetteComparisonRun") is not True
        or execution.get("stitchGraphConnectivityCheckRun") is not True
        or execution.get("sourceImageVisualComparisonRun") is not False
        or execution.get("providerAppearanceComparisonRun") is not False
        or execution.get("humanVisualReviewRun") is not False
        or execution.get("visualFidelityReviewRun") is not False
        or execution.get("singleShellWeldProofRun") is not False
        or execution.get("singleShellWeldExecutionRun") is not False
        or execution.get("meshStitchOrWeldExecutionRun") is not stitched_execution_run
    ):
        issues.append(
            _issue(
                "geometry_visual_shell_review_execution_state_invalid",
                "fatal",
                "reports/geometry_visual_shell_review.json",
                (
                    "Visual/shell review must run deterministic review and shell proof, "
                    "and must leave clean/canonical acceptance to the clean gate."
                ),
            )
        )
    rendered_pixel_run = execution.get("renderedPixelComparisonRun")
    if not isinstance(rendered_pixel_run, bool):
        issues.append(
            _issue(
                "geometry_visual_shell_review_execution_state_invalid",
                "fatal",
                "reports/geometry_visual_shell_review.json",
                "Visual/shell review renderedPixelComparisonRun must be a boolean.",
            )
        )
    if (
        readiness.get("status") != "visual_shell_review_completed_clean_rejected"
        or readiness.get("acceptedForVisualFidelity") is not False
        or readiness.get("sourceImageVisualFidelityAccepted") is not False
        or readiness.get("providerAppearanceAccepted") is not False
        or readiness.get("singleShellWeldProven") is not False
        or readiness.get("meshStitchOrWeldProven") is not stitched_proven
        or readiness.get("acceptedForCleanProposal") is not False
        or readiness.get("acceptedForCanonical") is not False
        or readiness.get("acceptedForRuntimeRender")
        != runtime_result.get("readiness", {}).get("acceptedForRuntimeRender")
    ):
        issues.append(
            _issue(
                "geometry_visual_shell_review_acceptance_invalid",
                "fatal",
                "reports/geometry_visual_shell_review.json",
                ("Visual/shell review cannot accept clean or canonical geometry."),
            )
        )
    if (
        aggregate.get("visualFidelityReviewRun") is not False
        or aggregate.get("representationSilhouetteComparisonRun") is not True
        or aggregate.get("representationSilhouetteAccepted") is not True
        or aggregate.get("sourceImageVisualComparisonRun") is not False
        or aggregate.get("sourceImageVisualFidelityAccepted") is not False
        or aggregate.get("providerAppearanceComparisonRun") is not False
        or aggregate.get("providerAppearanceAccepted") is not False
        or aggregate.get("humanVisualReviewRun") is not False
        or aggregate.get("stitchGraphConnectivityCheckRun") is not True
        or aggregate.get("stitchGraphConnectable") is not True
        or aggregate.get("singleShellWeldProofRun") is not False
        or aggregate.get("singleShellWeldProven") is not False
        or aggregate.get("meshStitchOrWeldExecutionRun") is not stitched_execution_run
        or aggregate.get("meshStitchOrWeldProven") is not stitched_proven
        or aggregate.get("acceptedForCleanProposal") is not False
        or aggregate.get("acceptedForCanonical") is not False
        or _int_or(aggregate.get("vertexCount"), 0) <= 0
        or _int_or(aggregate.get("triangleCount"), 0) <= 0
    ):
        issues.append(
            _issue(
                "geometry_visual_shell_review_aggregate_invalid",
                "fatal",
                "reports/geometry_visual_shell_review.json",
                "Visual/shell review aggregate must record a completed but rejected review.",
            )
        )
    shell_proof = visual_shell.get("shellProof", {})
    if (
        not isinstance(shell_proof, dict)
        or shell_proof.get("meshStitchOrWeldExecutionRun") is not stitched_execution_run
        or shell_proof.get("meshStitchOrWeldProven") is not stitched_proven
        or shell_proof.get("meshStitchOrWeldOutputAssetPath")
        != stitched_shell.get("renderAsset", {}).get("path")
        or shell_proof.get("meshStitchOrWeldOutputTopologyHash")
        != stitched_shell.get("renderAsset", {}).get("topologyHash")
        or shell_proof.get("meshStitchOrWeldOutputContentHash")
        != stitched_shell.get("renderAsset", {}).get("contentHash")
        or shell_proof.get("meshStitchOrWeldAudit") != stitched_shell.get("topologyAudit")
        or shell_proof.get("singleShellWeldExecutionRun") is not False
        or shell_proof.get("singleShellWeldProofRun") is not False
        or shell_proof.get("singleShellWeldProven") is not False
    ):
        issues.append(
            _issue(
                "geometry_visual_shell_review_weld_claim_invalid",
                "fatal",
                "reports/geometry_visual_shell_review.json",
                (
                    "Visual/shell review cannot claim mesh stitch/weld execution without "
                    "an output asset audit."
                ),
            )
        )
    appearance = visual_shell.get("appearanceEvidence", {})
    if (
        not isinstance(appearance, dict)
        or appearance.get("sourceImageVisualComparisonRun") is not False
        or appearance.get("sourceImageVisualFidelityAccepted") is not False
        or appearance.get("providerAppearanceComparisonRun") is not False
        or appearance.get("providerAppearanceAccepted") is not False
        or appearance.get("humanVisualReviewRun") is not False
        or appearance.get("humanVisualReviewResult") != "not_run"
    ):
        issues.append(
            _issue(
                "geometry_visual_shell_review_visual_fidelity_claim_invalid",
                "fatal",
                "reports/geometry_visual_shell_review.json",
                (
                    "Source/provider/human visual-fidelity claims require independent "
                    "reference evidence."
                ),
            )
        )
    if quality.get("status") != "reviewed_clean_rejected":
        issues.append(
            _issue(
                "geometry_visual_shell_review_quality_status_invalid",
                "fatal",
                "reports/geometry_visual_shell_review.json",
                "Visual/shell review quality must remain rejected for clean geometry.",
            )
        )
    if (
        policy.get("allowExternalApis") is not False
        or policy.get("allowTrainingUse") is not False
        or policy.get("containsUserImagery") is not False
        or policy.get("containsPersonalBodyData") is not False
        or policy.get("approvedDomain") != "avatar_and_garment_only"
    ):
        issues.append(
            _issue(
                "geometry_visual_shell_review_policy_violation",
                "fatal",
                "reports/geometry_visual_shell_review.json",
                "Visual/shell review cannot permit external APIs, training use or user data.",
            )
        )
    caps = manifest.get("capabilities", {})
    if isinstance(caps, dict) and caps.get("geometryVisualShellReviewAvailable") is not True:
        issues.append(
            _issue(
                "geometry_visual_shell_review_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest capability geometryVisualShellReviewAvailable must be true.",
            )
        )
    if _contains_nonfinite(visual_shell):
        issues.append(
            _issue(
                "geometry_visual_shell_review_nonfinite_numeric_value",
                "fatal",
                "reports/geometry_visual_shell_review.json",
                "Visual/shell review report must not contain NaN or Infinity.",
            )
        )


def _validate_inspection_artifacts(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    artifact_manifest = _read_required_json(package_dir, "reports/inspection/manifest.json", issues)
    report = _read_required_json(package_dir, "reports/inspection/inspection_report.json", issues)
    if artifact_manifest is None or report is None:
        return

    if artifact_manifest.get("garmentId") != manifest.get("garmentId") or report.get(
        "garmentId"
    ) != manifest.get("garmentId"):
        issues.append(
            _issue(
                "inspection_artifact_garment_mismatch",
                "fatal",
                "reports/inspection/inspection_report.json",
                "Inspection artifacts must reference the package garment ID.",
            )
        )
    if artifact_manifest.get("garmentClass") != manifest.get("garmentClass") or report.get(
        "garmentClass"
    ) != manifest.get("garmentClass"):
        issues.append(
            _issue(
                "inspection_artifact_class_mismatch",
                "fatal",
                "reports/inspection/inspection_report.json",
                "Inspection artifacts must reference the package garment class.",
            )
        )

    if _nested_string(artifact_manifest, ["integrity", "inspectionManifestHash"], "") != (
        hash_inspection_artifact_manifest(artifact_manifest)
    ):
        issues.append(
            _issue(
                "inspection_manifest_hash_mismatch",
                "fatal",
                "reports/inspection/manifest.json",
                "Inspection artifact manifest hash must match its canonical payload.",
            )
        )
    if _nested_string(report, ["integrity", "inspectionReportHash"], "") != (
        hash_inspection_artifact_report(report)
    ):
        issues.append(
            _issue(
                "inspection_report_hash_mismatch",
                "fatal",
                "reports/inspection/inspection_report.json",
                "Inspection artifact report hash must match its canonical payload.",
            )
        )
    if report.get("manifestHash") != _nested_string(
        artifact_manifest, ["integrity", "inspectionManifestHash"], ""
    ):
        issues.append(
            _issue(
                "inspection_report_manifest_hash_mismatch",
                "fatal",
                "reports/inspection/inspection_report.json",
                "Inspection report must reference the inspection manifest hash.",
            )
        )

    expected_specs = {str(spec["artifactId"]): spec for spec in required_artifact_specs()}
    expected_ids = set(expected_specs)
    artifacts = artifact_manifest.get("artifacts", [])
    if not isinstance(artifacts, list):
        issues.append(
            _issue(
                "inspection_artifacts_invalid",
                "fatal",
                "reports/inspection/manifest.json",
                "Inspection artifact manifest artifacts must be a list.",
            )
        )
        artifacts = []
    actual_ids = {str(artifact.get("artifactId", "")) for artifact in artifacts}
    if actual_ids != expected_ids:
        issues.append(
            _issue(
                "inspection_artifact_set_mismatch",
                "fatal",
                "reports/inspection/manifest.json",
                "Inspection artifact IDs must match the deterministic BP47 artifact set.",
            )
        )
    if _int_or(artifact_manifest.get("artifactCount"), -1) != len(artifacts):
        issues.append(
            _issue(
                "inspection_artifact_count_mismatch",
                "fatal",
                "reports/inspection/manifest.json",
                "Inspection artifactCount must match artifact records.",
            )
        )

    tier_status_by_name = {
        str(tier.get("tier")): tier for tier in artifact_manifest.get("evidenceTiers", [])
    }
    report_tier_status_by_name = {
        str(tier.get("tier")): tier for tier in report.get("evidenceTiers", [])
    }
    for tier in [
        "topology_representation_inspection",
        "canonical_simulation_to_render_silhouette_preservation",
        "independent_provider_geometry_appearance_comparison",
        "source_image_silhouette_comparison",
        "source_image_appearance_texture_logo_comparison",
        "human_visual_review",
    ]:
        if tier not in tier_status_by_name or tier not in report_tier_status_by_name:
            issues.append(
                _issue(
                    "inspection_evidence_tier_missing",
                    "fatal",
                    "reports/inspection/inspection_report.json",
                    "Inspection evidence tiers must remain explicit and separate.",
                    tier,
                )
            )

    for tier in [
        "independent_provider_geometry_appearance_comparison",
        "source_image_silhouette_comparison",
        "source_image_appearance_texture_logo_comparison",
        "human_visual_review",
    ]:
        for source in [tier_status_by_name, report_tier_status_by_name]:
            tier_doc = source.get(tier, {})
            if tier_doc.get("status") != "not_run" or tier_doc.get("accepted") is not False:
                issues.append(
                    _issue(
                        "inspection_evidence_tier_overclaimed",
                        "fatal",
                        "reports/inspection/inspection_report.json",
                        "Source/provider/human evidence tiers must remain not_run.",
                        tier,
                    )
                )

    readiness = report.get("readiness", {})
    if (
        not isinstance(readiness, dict)
        or readiness.get("topologyRepresentationInspectionRun") is not True
        or readiness.get("canonicalSimulationToRenderSilhouetteRun") is not True
        or readiness.get("providerGeometryAppearanceComparisonRun") is not False
        or readiness.get("sourceImageSilhouetteComparisonRun") is not False
        or readiness.get("sourceImageAppearanceComparisonRun") is not False
        or readiness.get("humanVisualReviewRun") is not False
        or readiness.get("acceptedForVisualFidelity") is not False
        or readiness.get("acceptedForCleanProposal") is not False
    ):
        issues.append(
            _issue(
                "inspection_readiness_overclaimed",
                "fatal",
                "reports/inspection/inspection_report.json",
                "BP47 inspection artifacts cannot unlock visual fidelity or clean acceptance.",
            )
        )

    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        artifact_id = str(artifact.get("artifactId", ""))
        spec = expected_specs.get(artifact_id)
        if spec is None:
            continue
        rel = str(artifact.get("path", ""))
        if rel != str(spec["path"]):
            issues.append(
                _issue(
                    "inspection_artifact_path_mismatch",
                    "fatal",
                    "reports/inspection/manifest.json",
                    "Inspection artifact path does not match its deterministic artifact ID.",
                    artifact_id,
                )
            )
            continue
        path = package_dir / rel
        if not path.exists():
            issues.append(
                _issue("inspection_artifact_missing", "fatal", rel, "Inspection artifact missing.")
            )
            continue
        if artifact.get("contentHash") != sha256_file(path):
            issues.append(
                _issue(
                    "inspection_artifact_hash_mismatch",
                    "fatal",
                    rel,
                    "Inspection artifact content hash is stale.",
                    artifact_id,
                )
            )
        if artifact.get("byteSize") != path.stat().st_size:
            issues.append(
                _issue(
                    "inspection_artifact_size_mismatch",
                    "fatal",
                    rel,
                    "Inspection artifact byte size is stale.",
                    artifact_id,
                )
            )
        try:
            svg_text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            svg_text = ""
            issues.append(
                _issue(
                    "inspection_artifact_not_utf8_svg",
                    "fatal",
                    rel,
                    "Inspection SVG must be UTF-8 text.",
                    artifact_id,
                )
            )
        if "<svg" not in svg_text or "</svg>" not in svg_text:
            issues.append(
                _issue(
                    "inspection_artifact_svg_invalid",
                    "fatal",
                    rel,
                    "Inspection artifact must decode as a simple SVG document.",
                    artifact_id,
                )
            )
        camera = artifact.get("camera", {})
        if (
            not isinstance(camera, dict)
            or camera.get("viewId") != spec["viewId"]
            or artifact.get("width") != 640
            or artifact.get("height") != 480
            or artifact.get("format") != "svg"
            or artifact.get("colorSpace") != "srgb"
            or artifact.get("overlayKind") != spec["overlayKind"]
            or artifact.get("evidenceTier") != spec["evidenceTier"]
            or artifact.get("syntheticPublicSafe") is not True
        ):
            issues.append(
                _issue(
                    "inspection_artifact_metadata_mismatch",
                    "fatal",
                    "reports/inspection/manifest.json",
                    "Inspection artifact metadata must match its deterministic view contract.",
                    artifact_id,
                )
            )
        source_hashes = artifact.get("sourceAssetHashes", {})
        if isinstance(source_hashes, dict):
            for relpath, declared_hash in source_hashes.items():
                source_path = package_dir / str(relpath)
                if not source_path.exists():
                    issues.append(
                        _issue(
                            "inspection_source_missing",
                            "fatal",
                            "reports/inspection/manifest.json",
                            "Inspection artifact source file is missing.",
                            str(relpath),
                        )
                    )
                elif declared_hash != sha256_file(source_path):
                    issues.append(
                        _issue(
                            "inspection_source_hash_mismatch",
                            "fatal",
                            "reports/inspection/manifest.json",
                            "Inspection artifact source hash is stale.",
                            str(relpath),
                        )
                    )
    report_sources = report.get("sourceHashes", {})
    if isinstance(report_sources, dict):
        for relpath, declared_hash in report_sources.items():
            source_path = package_dir / str(relpath)
            if source_path.exists() and declared_hash != sha256_file(source_path):
                issues.append(
                    _issue(
                        "inspection_report_source_hash_mismatch",
                        "fatal",
                        "reports/inspection/inspection_report.json",
                        "Inspection report source hash is stale.",
                        str(relpath),
                    )
                )
    caps = manifest.get("capabilities", {})
    if isinstance(caps, dict):
        if caps.get("deterministicInspectionArtifactsAvailable") is not True:
            issues.append(
                _issue(
                    "inspection_artifact_capability_missing",
                    "fatal",
                    "manifest.json",
                    "Manifest must declare deterministic inspection artifacts.",
                )
            )
        if caps.get("visualEvidenceTiersSeparated") is not True:
            issues.append(
                _issue(
                    "inspection_evidence_tier_capability_missing",
                    "fatal",
                    "manifest.json",
                    "Manifest must declare separated visual evidence tiers.",
                )
            )
    if _contains_nonfinite(artifact_manifest) or _contains_nonfinite(report):
        issues.append(
            _issue(
                "inspection_artifact_nonfinite_numeric_value",
                "fatal",
                "reports/inspection/inspection_report.json",
                "Inspection manifests and reports must not contain NaN or Infinity.",
            )
        )


def _validate_render_frame_pose_suite(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    report = _read_required_json(package_dir, "reports/render_frame_pose_suite.json", issues)
    sim_manifest = _read_required_json(package_dir, "simulation/mesh_manifest.json", issues)
    render_manifest = _read_required_json(package_dir, "render/mesh_manifest.json", issues)
    binding_manifest = _read_required_json(package_dir, "binding/binding_manifest.json", issues)
    if (
        report is None
        or sim_manifest is None
        or render_manifest is None
        or binding_manifest is None
    ):
        return
    if report.get("garmentId") != manifest.get("garmentId"):
        issues.append(
            _issue(
                "render_frame_pose_suite_garment_mismatch",
                "fatal",
                "reports/render_frame_pose_suite.json",
                "Render frame/pose suite must reference the package garment ID.",
            )
        )
    if report.get("garmentClass") != manifest.get("garmentClass"):
        issues.append(
            _issue(
                "render_frame_pose_suite_class_mismatch",
                "fatal",
                "reports/render_frame_pose_suite.json",
                "Render frame/pose suite must reference the package garment class.",
            )
        )
    if _nested_string(report, ["integrity", "renderFramePoseSuiteHash"], "") != (
        hash_render_frame_pose_suite_report(report)
    ):
        issues.append(
            _issue(
                "render_frame_pose_suite_hash_mismatch",
                "fatal",
                "reports/render_frame_pose_suite.json",
                "Render frame/pose suite hash must match its canonical payload.",
            )
        )
    source_assets = report.get("sourceAssets", {})
    if isinstance(source_assets, dict):
        for asset in source_assets.values():
            if not isinstance(asset, dict) or "path" not in asset or "sha256" not in asset:
                continue
            rel = str(asset["path"])
            path = package_dir / rel
            if not path.exists():
                issues.append(
                    _issue(
                        "render_frame_pose_suite_source_missing",
                        "fatal",
                        "reports/render_frame_pose_suite.json",
                        "A source artifact referenced by BP48 is missing.",
                        rel,
                    )
                )
            elif asset["sha256"] != sha256_file(path):
                issues.append(
                    _issue(
                        "render_frame_pose_suite_source_hash_mismatch",
                        "fatal",
                        "reports/render_frame_pose_suite.json",
                        "A source artifact hash referenced by BP48 is stale.",
                        rel,
                    )
                )
    try:
        glb_audit = audit_glb(package_dir / "render" / "fallback.glb")
    except Exception as exc:
        issues.append(
            _issue(
                "render_frame_pose_suite_glb_parse_failed",
                "fatal",
                "render/fallback.glb",
                str(exc),
            )
        )
        glb_audit = {}
    if glb_audit and not glb_audit.get("hasVec4Tangents", False):
        issues.append(
            _issue(
                "render_frame_pose_suite_tangent_accessor_missing",
                "fatal",
                "render/fallback.glb",
                "BP48 requires every render GLB primitive to persist TANGENT as VEC4.",
            )
        )
    readiness = report.get("readiness", {})
    frame = report.get("framePersistence", {})
    aggregate = report.get("aggregate", {})
    if (
        not isinstance(readiness, dict)
        or readiness.get("framePersistenceRun") is not True
        or readiness.get("glbTangentsPersisted") is not True
        or readiness.get("poseSuiteRun") is not True
        or readiness.get("poseSuitePass") is not True
        or readiness.get("acceptedForRuntimeFramePreview") is not True
        or readiness.get("acceptedForCleanProposal") is not False
        or readiness.get("acceptedForCanonical") is not False
        or not isinstance(frame, dict)
        or frame.get("tangentAccessorType") != "VEC4"
        or not isinstance(aggregate, dict)
        or aggregate.get("acceptedForRuntimeFramePreview") is not True
    ):
        issues.append(
            _issue(
                "render_frame_pose_suite_readiness_invalid",
                "fatal",
                "reports/render_frame_pose_suite.json",
                "BP48 may accept only runtime frame preview and must remain clean/canonical false.",
            )
        )
    try:
        binding = read_binding(package_dir / "binding" / "sim_to_render.bin")
        expected = build_render_frame_pose_suite_report(
            garment_id=str(manifest["garmentId"]),
            garment_class=str(manifest["garmentClass"]),
            render_asset_path=package_dir / "render" / "fallback.glb",
            render_asset_package_path="render/fallback.glb",
            simulation_mesh_manifest_path=package_dir / "simulation" / "mesh_manifest.json",
            render_mesh_manifest_path=package_dir / "render" / "mesh_manifest.json",
            binding_asset_path=package_dir / "binding" / "sim_to_render.bin",
            binding_manifest_path=package_dir / "binding" / "binding_manifest.json",
            simulation_mesh=_meshset_from_manifest(sim_manifest),
            render_mesh=_meshset_from_manifest(render_manifest),
            binding=binding,
            binding_manifest=binding_manifest,
        )
    except Exception as exc:
        issues.append(
            _issue(
                "render_frame_pose_suite_recompute_failed",
                "fatal",
                "reports/render_frame_pose_suite.json",
                str(exc),
            )
        )
        return
    for key in [
        "sourceAssets",
        "sourceHashes",
        "framePersistence",
        "poseSuite",
        "aggregate",
        "execution",
        "readiness",
        "policy",
        "limitations",
    ]:
        if report.get(key) != expected.get(key):
            issues.append(
                _issue(
                    "render_frame_pose_suite_recompute_mismatch",
                    "fatal",
                    "reports/render_frame_pose_suite.json",
                    "BP48 frame/pose evidence must recompute from package artifacts.",
                    key,
                )
            )
    caps = manifest.get("capabilities", {})
    if isinstance(caps, dict):
        if caps.get("renderTangentsPersistedAvailable") is not True:
            issues.append(
                _issue(
                    "render_tangents_capability_missing",
                    "fatal",
                    "manifest.json",
                    "Manifest must declare persisted render tangent availability.",
                )
            )
        if caps.get("poseSuiteBindingEvidenceAvailable") is not True:
            issues.append(
                _issue(
                    "pose_suite_binding_capability_missing",
                    "fatal",
                    "manifest.json",
                    "Manifest must declare pose-suite binding evidence availability.",
                )
            )
    if _contains_nonfinite(report):
        issues.append(
            _issue(
                "render_frame_pose_suite_nonfinite_numeric_value",
                "fatal",
                "reports/render_frame_pose_suite.json",
                "Render frame/pose suite report must not contain NaN or Infinity.",
            )
        )


def _validate_production_binding_contract(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    contract = _read_required_json(package_dir, "binding/production_binding_contract.json", issues)
    sim_manifest = _read_required_json(package_dir, "simulation/mesh_manifest.json", issues)
    render_manifest = _read_required_json(package_dir, "render/mesh_manifest.json", issues)
    binding_manifest = _read_required_json(package_dir, "binding/binding_manifest.json", issues)
    if (
        contract is None
        or sim_manifest is None
        or render_manifest is None
        or binding_manifest is None
    ):
        return
    if contract.get("garmentId") != manifest.get("garmentId"):
        issues.append(
            _issue(
                "production_binding_contract_garment_mismatch",
                "fatal",
                "binding/production_binding_contract.json",
                "Production binding contract must reference the package garment ID.",
            )
        )
    if contract.get("garmentClass") != manifest.get("garmentClass"):
        issues.append(
            _issue(
                "production_binding_contract_class_mismatch",
                "fatal",
                "binding/production_binding_contract.json",
                "Production binding contract must reference the package garment class.",
            )
        )
    if _nested_string(contract, ["integrity", "productionBindingContractHash"], "") != (
        hash_production_binding_contract(contract)
    ):
        issues.append(
            _issue(
                "production_binding_contract_hash_mismatch",
                "fatal",
                "binding/production_binding_contract.json",
                "Production binding contract hash must match its canonical payload.",
            )
        )
    try:
        binding = read_binding(package_dir / "binding" / "sim_to_render.bin")
        sim_mesh = _meshset_from_manifest(sim_manifest)
        render_mesh = _meshset_from_manifest(render_manifest)
    except Exception as exc:
        issues.append(
            _issue(
                "production_binding_contract_decode_failed",
                "fatal",
                "binding/production_binding_contract.json",
                str(exc),
            )
        )
        return
    source = contract.get("sourceSimulation", {})
    destination = contract.get("destinationRender", {})
    binary = contract.get("binaryBinding", {})
    records = contract.get("records", [])
    if not isinstance(records, list):
        issues.append(
            _issue(
                "production_binding_contract_records_invalid",
                "fatal",
                "binding/production_binding_contract.json",
                "Production binding records must be a list.",
            )
        )
        records = []
    if len(records) != render_mesh.vertex_count or len(records) != len(binding.records):
        issues.append(
            _issue(
                "production_binding_contract_record_count_mismatch",
                "fatal",
                "binding/production_binding_contract.json",
                "Production binding contract must enumerate every render vertex exactly once.",
            )
        )
    stable_ids = [
        str(record.get("renderVertexId")) for record in records if isinstance(record, dict)
    ]
    if len(stable_ids) != len(set(stable_ids)):
        issues.append(
            _issue(
                "production_binding_contract_duplicate_render_vertex_id",
                "fatal",
                "binding/production_binding_contract.json",
                "Stable render vertex IDs must be unique.",
            )
        )
    if set(stable_ids) != {f"rv.{index:06d}" for index in range(render_mesh.vertex_count)}:
        issues.append(
            _issue(
                "production_binding_contract_missing_render_vertex_id",
                "fatal",
                "binding/production_binding_contract.json",
                "Stable render vertex IDs must cover the destination render mesh.",
            )
        )
    if source.get("topologyHash") != topology_hash(sim_mesh):
        issues.append(
            _issue(
                "production_binding_contract_source_topology_stale",
                "fatal",
                "binding/production_binding_contract.json",
                "Source simulation topology hash is stale.",
            )
        )
    if source.get("contentHash") != geometry_content_hash(sim_mesh):
        issues.append(
            _issue(
                "production_binding_contract_source_content_stale",
                "fatal",
                "binding/production_binding_contract.json",
                "Source simulation content hash is stale.",
            )
        )
    if destination.get("topologyHash") != topology_hash(render_mesh):
        issues.append(
            _issue(
                "production_binding_contract_render_topology_stale",
                "fatal",
                "binding/production_binding_contract.json",
                "Destination render topology hash is stale.",
            )
        )
    if destination.get("contentHash") != geometry_content_hash(render_mesh):
        issues.append(
            _issue(
                "production_binding_contract_render_content_stale",
                "fatal",
                "binding/production_binding_contract.json",
                "Destination render content hash is stale.",
            )
        )
    if binary.get("simulationTopologyHash") != binding.simulation_topology_hash:
        issues.append(
            _issue(
                "production_binding_contract_binary_sim_hash_mismatch",
                "fatal",
                "binding/production_binding_contract.json",
                "Binary binding simulation topology hash mismatch.",
            )
        )
    if binary.get("renderTopologyHash") != binding.render_topology_hash:
        issues.append(
            _issue(
                "production_binding_contract_binary_render_hash_mismatch",
                "fatal",
                "binding/production_binding_contract.json",
                "Binary binding render topology hash mismatch.",
            )
        )
    safeguards = contract.get("safeguards", {})
    if (
        not isinstance(safeguards, dict)
        or int(safeguards.get("invalidOpeningCrossingCount", 1)) != 0
    ):
        issues.append(
            _issue(
                "production_binding_contract_opening_crossing",
                "fatal",
                "binding/production_binding_contract.json",
                "Production binding must not cross semantic openings.",
            )
        )
    if _contains_nonfinite(contract):
        issues.append(
            _issue(
                "production_binding_contract_nonfinite_numeric_value",
                "fatal",
                "binding/production_binding_contract.json",
                "Production binding contract must not contain NaN or Infinity.",
            )
        )


def _validate_production_binding_c3(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    report = _read_required_json(package_dir, "reports/production_binding_c3.json", issues)
    if report is None:
        return
    if report.get("garmentId") != manifest.get("garmentId"):
        issues.append(
            _issue(
                "production_binding_c3_garment_mismatch",
                "fatal",
                "reports/production_binding_c3.json",
                "Production binding C3 report must reference the package garment ID.",
            )
        )
    if report.get("garmentClass") != manifest.get("garmentClass"):
        issues.append(
            _issue(
                "production_binding_c3_class_mismatch",
                "fatal",
                "reports/production_binding_c3.json",
                "Production binding C3 report must reference the package garment class.",
            )
        )
    if _nested_string(report, ["integrity", "productionBindingC3ReportHash"], "") != (
        hash_production_binding_c3_report(report)
    ):
        issues.append(
            _issue(
                "production_binding_c3_hash_mismatch",
                "fatal",
                "reports/production_binding_c3.json",
                "Production binding C3 report hash must match its canonical payload.",
            )
        )
    source_assets = report.get("sourceAssets", {})
    if isinstance(source_assets, dict):
        for asset in source_assets.values():
            if not isinstance(asset, dict) or "path" not in asset or "sha256" not in asset:
                continue
            rel = str(asset["path"])
            path = package_dir / rel
            if not path.exists():
                issues.append(
                    _issue(
                        "production_binding_c3_source_missing",
                        "fatal",
                        "reports/production_binding_c3.json",
                        "A C3 source artifact is missing.",
                        rel,
                    )
                )
            elif asset["sha256"] != sha256_file(path):
                issues.append(
                    _issue(
                        "production_binding_c3_source_hash_mismatch",
                        "fatal",
                        "reports/production_binding_c3.json",
                        "A C3 source artifact hash is stale.",
                        rel,
                    )
                )
    try:
        expected = build_production_binding_c3_report_from_package(
            package_dir=package_dir,
            garment_id=str(manifest["garmentId"]),
            garment_class=str(manifest["garmentClass"]),
        )
    except Exception as exc:
        issues.append(
            _issue(
                "production_binding_c3_recompute_failed",
                "fatal",
                "reports/production_binding_c3.json",
                str(exc),
            )
        )
        return
    for key in [
        "sourceAssets",
        "bindingTrackInventory",
        "persistedValidation",
        "thresholds",
        "motionSuite",
        "aggregate",
        "performanceProfile",
        "execution",
        "capabilities",
        "readiness",
        "policy",
        "limitations",
    ]:
        if report.get(key) != expected.get(key):
            issues.append(
                _issue(
                    "production_binding_c3_recompute_mismatch",
                    "fatal",
                    "reports/production_binding_c3.json",
                    "Production binding C3 report must recompute from package artifacts.",
                    key,
                )
            )
    readiness = report.get("readiness", {})
    if (
        not isinstance(readiness, dict)
        or readiness.get("gateC3Status") != "complete_for_d0_fixed_avatar_tshirt_profile"
        or readiness.get("acceptedForD0RuntimeBindingProfile") is not True
        or readiness.get("acceptedForGlobalPhase6") is not False
        or readiness.get("acceptedForCleanProposal") is not False
        or readiness.get("acceptedForCanonical") is not False
    ):
        issues.append(
            _issue(
                "production_binding_c3_readiness_invalid",
                "fatal",
                "reports/production_binding_c3.json",
                "C3 may pass only for the D0 fixed-avatar T-shirt profile.",
            )
        )
    caps = manifest.get("capabilities", {})
    if isinstance(caps, dict):
        if caps.get("productionBindingC3ProfileAvailable") is not True:
            issues.append(
                _issue(
                    "production_binding_c3_capability_missing",
                    "fatal",
                    "manifest.json",
                    "Manifest must declare scoped production binding C3 evidence.",
                )
            )
        if caps.get("productionBindingContractAvailable") is not True:
            issues.append(
                _issue(
                    "production_binding_contract_capability_missing",
                    "fatal",
                    "manifest.json",
                    "Manifest must declare the production binding contract.",
                )
            )
    if _contains_nonfinite(report):
        issues.append(
            _issue(
                "production_binding_c3_nonfinite_numeric_value",
                "fatal",
                "reports/production_binding_c3.json",
                "Production binding C3 report must not contain NaN or Infinity.",
            )
        )


def _validate_geometry_clean_acceptance_gate(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    runtime_result = _read_required_json(
        package_dir, "reports/geometry_runtime_binding_result.json", issues
    )
    semantic_transfer = _read_required_json(
        package_dir, "reports/geometry_semantic_transfer.json", issues
    )
    texture_identity = _read_required_json(package_dir, "textures/texture_identity.json", issues)
    material_uv_transfer = _read_required_json(
        package_dir, "reports/geometry_material_uv_transfer.json", issues
    )
    visual_shell_review = _read_required_json(
        package_dir, "reports/geometry_visual_shell_review.json", issues
    )
    provider_registry = _read_required_json(package_dir, "proposals/provider_registry.json", issues)
    clean_gate = _read_required_json(
        package_dir, "reports/geometry_clean_acceptance_gate.json", issues
    )
    if (
        runtime_result is None
        or semantic_transfer is None
        or texture_identity is None
        or material_uv_transfer is None
        or visual_shell_review is None
        or provider_registry is None
        or clean_gate is None
    ):
        return

    if clean_gate.get("garmentId") != manifest.get("garmentId"):
        issues.append(
            _issue(
                "geometry_clean_acceptance_gate_garment_mismatch",
                "fatal",
                "reports/geometry_clean_acceptance_gate.json",
                "Clean acceptance gate must reference the package garment ID.",
            )
        )
    if clean_gate.get("garmentClass") != manifest.get("garmentClass"):
        issues.append(
            _issue(
                "geometry_clean_acceptance_gate_class_mismatch",
                "fatal",
                "reports/geometry_clean_acceptance_gate.json",
                "Clean acceptance gate must reference the package garment class.",
            )
        )

    expected_sources = [
        (
            "sourceGeometryRuntimeBindingResultId",
            runtime_result.get("reportId"),
            "geometry_clean_acceptance_gate_runtime_source_mismatch",
        ),
        (
            "sourceGeometrySemanticTransferId",
            semantic_transfer.get("reportId"),
            "geometry_clean_acceptance_gate_semantic_source_mismatch",
        ),
        (
            "sourceTextureIdentityId",
            texture_identity.get("textureIdentityId"),
            "geometry_clean_acceptance_gate_texture_source_mismatch",
        ),
        (
            "sourceGeometryMaterialUvTransferId",
            material_uv_transfer.get("reportId"),
            "geometry_clean_acceptance_gate_material_uv_source_mismatch",
        ),
        (
            "sourceGeometryVisualShellReviewId",
            visual_shell_review.get("reportId"),
            "geometry_clean_acceptance_gate_visual_shell_source_mismatch",
        ),
        (
            "sourceProviderRegistryId",
            provider_registry.get("registryId"),
            "geometry_clean_acceptance_gate_registry_source_mismatch",
        ),
    ]
    for field, expected_value, code in expected_sources:
        if clean_gate.get(field) != expected_value:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "reports/geometry_clean_acceptance_gate.json",
                    f"Clean acceptance gate {field} must match its source artifact.",
                )
            )

    expected_hashes = [
        (
            "sourceGeometryRuntimeBindingResultHash",
            _nested_string(runtime_result, ["integrity", "geometryRuntimeBindingResultHash"], ""),
            "geometry_clean_acceptance_gate_runtime_hash_mismatch",
        ),
        (
            "sourceGeometrySemanticTransferHash",
            _nested_string(semantic_transfer, ["integrity", "geometrySemanticTransferHash"], ""),
            "geometry_clean_acceptance_gate_semantic_hash_mismatch",
        ),
        (
            "sourceTextureIdentityHash",
            _nested_string(texture_identity, ["integrity", "textureIdentityHash"], ""),
            "geometry_clean_acceptance_gate_texture_hash_mismatch",
        ),
        (
            "sourceGeometryMaterialUvTransferHash",
            _nested_string(
                material_uv_transfer,
                ["integrity", "geometryMaterialUvTransferHash"],
                "",
            ),
            "geometry_clean_acceptance_gate_material_uv_hash_mismatch",
        ),
        (
            "sourceGeometryVisualShellReviewHash",
            _nested_string(
                visual_shell_review,
                ["integrity", "geometryVisualShellReviewHash"],
                "",
            ),
            "geometry_clean_acceptance_gate_visual_shell_hash_mismatch",
        ),
        (
            "sourceProviderRegistryHash",
            _nested_string(provider_registry, ["integrity", "providerRegistryHash"], ""),
            "geometry_clean_acceptance_gate_registry_hash_mismatch",
        ),
    ]
    for field, expected_hash, code in expected_hashes:
        if clean_gate.get(field) != expected_hash:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "reports/geometry_clean_acceptance_gate.json",
                    f"Clean acceptance gate {field} must match its source artifact.",
                )
            )

    if _nested_string(clean_gate, ["integrity", "geometryCleanAcceptanceGateHash"], "") != (
        hash_geometry_clean_acceptance_gate(clean_gate)
    ):
        issues.append(
            _issue(
                "geometry_clean_acceptance_gate_hash_mismatch",
                "fatal",
                "reports/geometry_clean_acceptance_gate.json",
                "Clean acceptance gate hash must match its canonical payload.",
            )
        )

    candidate = clean_gate.get("candidate", {})
    measurements = clean_gate.get("measurements", {})
    thresholds = clean_gate.get("thresholds", {})
    checks = clean_gate.get("checks", [])
    aggregate = clean_gate.get("aggregate", {})
    execution = clean_gate.get("execution", {})
    readiness = clean_gate.get("readiness", {})
    quality = clean_gate.get("quality", {})
    policy = clean_gate.get("policy", {})
    for name, block in [
        ("candidate", candidate),
        ("measurements", measurements),
        ("thresholds", thresholds),
        ("aggregate", aggregate),
        ("execution", execution),
        ("readiness", readiness),
        ("quality", quality),
        ("policy", policy),
    ]:
        if not isinstance(block, dict):
            issues.append(
                _issue(
                    "geometry_clean_acceptance_gate_block_invalid",
                    "fatal",
                    "reports/geometry_clean_acceptance_gate.json",
                    f"Clean acceptance gate {name} block must be an object.",
                )
            )
            return
    if not isinstance(checks, list):
        issues.append(
            _issue(
                "geometry_clean_acceptance_gate_block_invalid",
                "fatal",
                "reports/geometry_clean_acceptance_gate.json",
                "Clean acceptance gate checks block must be a list.",
            )
        )
        return

    expected_gate = build_geometry_clean_acceptance_gate_report(
        garment_id=str(manifest.get("garmentId", "")),
        garment_class=str(manifest.get("garmentClass", "")),
        runtime_binding_result_report=runtime_result,
        semantic_transfer_report=semantic_transfer,
        texture_identity_report=texture_identity,
        material_uv_transfer_report=material_uv_transfer,
        visual_shell_review_report=visual_shell_review,
        provider_registry=provider_registry,
    )
    for key in [
        "candidate",
        "measurements",
        "thresholds",
        "checks",
        "aggregate",
        "execution",
        "readiness",
        "quality",
        "policy",
    ]:
        if clean_gate.get(key) != expected_gate.get(key):
            issues.append(
                _issue(
                    "geometry_clean_acceptance_gate_recompute_mismatch",
                    "fatal",
                    "reports/geometry_clean_acceptance_gate.json",
                    f"Clean acceptance gate field {key} is stale.",
                )
            )

    visual_mesh_stitch_execution_run = bool(
        visual_shell_review.get("execution", {}).get("meshStitchOrWeldExecutionRun") is True
    )

    if (
        execution.get("cleanAcceptanceGateRun") is not True
        or execution.get("runtimeBindingEvidenceReviewed") is not True
        or execution.get("semanticTransferEvidenceReviewed") is not True
        or execution.get("materialEvidenceReviewed") is not True
        or execution.get("policyReviewed") is not True
        or execution.get("visualFidelityReviewRun") is not False
        or execution.get("representationSilhouetteComparisonRun") is not True
        or execution.get("sourceImageVisualComparisonRun") is not False
        or execution.get("providerAppearanceComparisonRun") is not False
        or execution.get("uvTransferRun") is not True
        or execution.get("materialTransferRun") is not True
        or execution.get("materialTransferAccepted") is not True
        or execution.get("stitchGraphConnectivityCheckRun") is not True
        or execution.get("singleShellWeldProofRun") is not False
        or execution.get("meshStitchOrWeldExecutionRun") is not visual_mesh_stitch_execution_run
    ):
        issues.append(
            _issue(
                "geometry_clean_acceptance_gate_execution_state_invalid",
                "fatal",
                "reports/geometry_clean_acceptance_gate.json",
                (
                    "Clean acceptance gate may review deterministic runtime evidence but "
                    "must keep clean/canonical acceptance separate."
                ),
            )
        )
    if (
        readiness.get("status")
        not in {
            "clean_acceptance_rejected_representation_failed",
            "clean_acceptance_rejected_independent_visual_not_run",
            "clean_acceptance_rejected_visual_shell_failed",
            "clean_acceptance_rejected_mesh_stitch_weld_pending",
            "clean_acceptance_rejected_continuity_warn",
        }
        or readiness.get("acceptedForCleanProposal") is not False
        or readiness.get("acceptedForCanonical") is not False
        or readiness.get("acceptedForSimulation") is not False
        or readiness.get("acceptedForRuntimeRender")
        != runtime_result.get("readiness", {}).get("acceptedForRuntimeRender")
    ):
        issues.append(
            _issue(
                "geometry_clean_acceptance_gate_acceptance_invalid",
                "fatal",
                "reports/geometry_clean_acceptance_gate.json",
                "Clean acceptance gate cannot accept D0 clean/canonical geometry.",
            )
        )
    if quality.get("status") != "rejected":
        issues.append(
            _issue(
                "geometry_clean_acceptance_gate_quality_status_invalid",
                "fatal",
                "reports/geometry_clean_acceptance_gate.json",
                "D0 clean acceptance gate must remain rejected.",
            )
        )
    if (
        _int_or(aggregate.get("checkCount"), -1) != len(checks)
        or _int_or(aggregate.get("passedCheckCount"), -1)
        != sum(check.get("status") == "pass" for check in checks)
        or _int_or(aggregate.get("failedCheckCount"), -1)
        != sum(check.get("status") == "fail" for check in checks)
        or _int_or(aggregate.get("warningCheckCount"), -1)
        != sum(check.get("status") == "warn" for check in checks)
        or _int_or(aggregate.get("notRunCheckCount"), -1)
        != sum(check.get("status") == "not_run" for check in checks)
        or aggregate.get("acceptedForCleanProposal") is not False
        or aggregate.get("acceptedForCanonical") is not False
        or aggregate.get("acceptedForSimulation") is not False
        or aggregate.get("acceptedForRuntimeRender")
        != runtime_result.get("readiness", {}).get("acceptedForRuntimeRender")
    ):
        issues.append(
            _issue(
                "geometry_clean_acceptance_gate_aggregate_invalid",
                "fatal",
                "reports/geometry_clean_acceptance_gate.json",
                "Clean acceptance gate aggregate must mirror its checks and rejection state.",
            )
        )
    blocking_reasons = readiness.get("blockingReasons", [])
    rejection_reasons = quality.get("rejectionReasons", [])
    if not isinstance(blocking_reasons, list):
        blocking_reasons = []
    if not isinstance(rejection_reasons, list):
        rejection_reasons = []
    for reason in CLEAN_ACCEPTANCE_GATE_REJECTION_REASONS:
        if reason not in blocking_reasons or reason not in rejection_reasons:
            issues.append(
                _issue(
                    "geometry_clean_acceptance_gate_rejection_reason_missing",
                    "fatal",
                    "reports/geometry_clean_acceptance_gate.json",
                    "Clean acceptance gate must retain all canonical rejection reasons.",
                    reason,
                )
            )
    if (
        policy.get("allowExternalApis") is not False
        or policy.get("allowTrainingUse") is not False
        or policy.get("containsUserImagery") is not False
        or policy.get("containsPersonalBodyData") is not False
        or policy.get("approvedDomain") != "avatar_and_garment_only"
        or policy.get("providerOutputMayBecomeCanonicalWithoutGate") is not False
    ):
        issues.append(
            _issue(
                "geometry_clean_acceptance_gate_policy_violation",
                "fatal",
                "reports/geometry_clean_acceptance_gate.json",
                "Clean acceptance gate cannot permit external APIs, training use or user data.",
            )
        )
    caps = manifest.get("capabilities", {})
    if isinstance(caps, dict) and caps.get("geometryCleanAcceptanceGateAvailable") is not True:
        issues.append(
            _issue(
                "geometry_clean_acceptance_gate_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest capability geometryCleanAcceptanceGateAvailable must be true.",
            )
        )
    if _contains_nonfinite(clean_gate):
        issues.append(
            _issue(
                "geometry_clean_acceptance_gate_nonfinite_numeric_value",
                "fatal",
                "reports/geometry_clean_acceptance_gate.json",
                "Clean acceptance gate must not contain NaN or Infinity.",
            )
        )


def _validate_runtime_binding_result_file_reference(
    package_dir: Path,
    expected_path: str,
    asset: dict[str, Any],
    code_prefix: str,
    issues: list[ValidationIssue],
) -> Path | None:
    path_value = asset.get("path")
    if not isinstance(path_value, str):
        issues.append(
            _issue(
                f"{code_prefix}_path_invalid",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime binding result asset path must be package-relative.",
            )
        )
        return None
    try:
        validate_package_relpath(path_value)
    except ValueError:
        issues.append(
            _issue(
                f"{code_prefix}_path_invalid",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime binding result asset path is unsafe.",
            )
        )
        return None
    if expected_path and path_value != expected_path:
        issues.append(
            _issue(
                f"{code_prefix}_path_mismatch",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime binding result asset path does not match the expected source.",
            )
        )
    asset_path = package_dir / path_value
    if not asset_path.exists():
        issues.append(
            _issue(
                f"{code_prefix}_missing",
                "fatal",
                path_value,
                "Runtime binding result asset is missing.",
            )
        )
        return None
    if asset.get("sourceAssetHash") != sha256_file(asset_path):
        issues.append(
            _issue(
                f"{code_prefix}_hash_mismatch",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime binding result asset hash is stale.",
            )
        )
    if asset.get("byteSize") != asset_path.stat().st_size:
        issues.append(
            _issue(
                f"{code_prefix}_size_mismatch",
                "fatal",
                "reports/geometry_runtime_binding_result.json",
                "Runtime binding result asset byte size is stale.",
            )
        )
    return asset_path


def _validate_provider_registry(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    capture_record = _read_required_json(package_dir, "source/capture_record.json", issues)
    visual = _read_required_json(package_dir, "source/visual_observations.json", issues)
    fit_report = _read_required_json(package_dir, "fitting/tshirt_fit.json", issues)
    texture = _read_required_json(package_dir, "textures/texture_identity.json", issues)
    proposal = _read_required_json(package_dir, "proposals/raw_geometry_proposal.json", issues)
    registry = _read_required_json(package_dir, "proposals/provider_registry.json", issues)
    registry_quality = _read_required_json(
        package_dir, "reports/provider_registry_quality.json", issues
    )
    if (
        capture_record is None
        or visual is None
        or fit_report is None
        or texture is None
        or proposal is None
        or registry is None
    ):
        return

    if registry.get("garmentId") != manifest.get("garmentId"):
        issues.append(
            _issue(
                "provider_registry_garment_mismatch",
                "fatal",
                "proposals/provider_registry.json",
                "Provider registry must reference the package garment ID.",
            )
        )
    if registry.get("garmentClass") != manifest.get("garmentClass"):
        issues.append(
            _issue(
                "provider_registry_class_mismatch",
                "fatal",
                "proposals/provider_registry.json",
                "Provider registry must reference the package garment class.",
            )
        )

    expected_hashes = [
        (
            "sourceRecordHash",
            _nested_string(capture_record, ["immutability", "sourceRecordHash"], ""),
            "provider_registry_source_hash_mismatch",
        ),
        (
            "sourceVisualRecordHash",
            _nested_string(visual, ["integrity", "visualRecordHash"], ""),
            "provider_registry_visual_hash_mismatch",
        ),
        (
            "sourceFitReportHash",
            _nested_string(fit_report, ["integrity", "fitReportHash"], ""),
            "provider_registry_fit_hash_mismatch",
        ),
        (
            "sourceTextureIdentityHash",
            _nested_string(texture, ["integrity", "textureIdentityHash"], ""),
            "provider_registry_texture_hash_mismatch",
        ),
        (
            "sourceGeometryProposalHash",
            _nested_string(proposal, ["integrity", "geometryProposalHash"], ""),
            "provider_registry_proposal_hash_mismatch",
        ),
    ]
    for field, expected_hash, code in expected_hashes:
        if registry.get(field) != expected_hash:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "proposals/provider_registry.json",
                    f"Provider registry {field} must match its source artifact.",
                )
            )

    if _nested_string(registry, ["integrity", "providerRegistryHash"], "") != (
        hash_provider_registry(registry)
    ):
        issues.append(
            _issue(
                "provider_registry_hash_mismatch",
                "fatal",
                "proposals/provider_registry.json",
                "Provider registry hash must match its canonical payload.",
            )
        )

    scope = registry.get("scope", {})
    policy = registry.get("policy", {})
    providers = registry.get("providers", [])
    d0_caps = registry.get("d0Capabilities", {})
    manual = registry.get("manualImportCandidate", {})
    for name, block in [
        ("scope", scope),
        ("policy", policy),
        ("d0Capabilities", d0_caps),
        ("manualImportCandidate", manual),
    ]:
        if not isinstance(block, dict):
            issues.append(
                _issue(
                    "provider_registry_block_invalid",
                    "fatal",
                    "proposals/provider_registry.json",
                    f"Provider registry {name} block must be an object.",
                )
            )
            return
    if not isinstance(providers, list) or not providers:
        issues.append(
            _issue(
                "provider_registry_provider_list_invalid",
                "fatal",
                "proposals/provider_registry.json",
                "Provider registry must list at least one provider.",
            )
        )
        providers = []

    selected_provider = str(registry.get("selectedProviderId", ""))
    provider_id_list = [
        str(provider.get("providerId", "")) for provider in providers if isinstance(provider, dict)
    ]
    provider_ids = set(provider_id_list)
    if len(provider_id_list) != len(provider_ids):
        issues.append(
            _issue(
                "provider_registry_duplicate_provider_id",
                "fatal",
                "proposals/provider_registry.json",
                "Provider registry provider IDs must be unique.",
            )
        )
    if selected_provider not in provider_ids:
        issues.append(
            _issue(
                "provider_registry_selected_provider_missing",
                "fatal",
                "proposals/provider_registry.json",
                "Selected provider must be present in provider list.",
            )
        )
    allowed_selected = {
        "closy.null_geometry_proposal_provider.v1",
        "closy.manual_local_glb_import.v1",
    }
    if selected_provider not in allowed_selected:
        issues.append(
            _issue(
                "provider_registry_selected_provider_invalid",
                "fatal",
                "proposals/provider_registry.json",
                "Selected geometry provider is not supported by v1 validation.",
            )
        )

    if (
        scope.get("supportedDomain") != "avatar_garment_only"
        or scope.get("allowsGenericObjects") is not False
        or "garment_visual_geometry_proposal" not in scope.get("supportedPurposes", [])
        or manifest.get("garmentClass") not in scope.get("supportedGarmentClasses", [])
    ):
        issues.append(
            _issue(
                "provider_registry_domain_invalid",
                "fatal",
                "proposals/provider_registry.json",
                (
                    "Provider registry must remain constrained to avatar-and-garment "
                    "geometry proposals."
                ),
            )
        )
    if (
        policy.get("allowExternalApis") is not False
        or policy.get("allowTrainingUse") is not False
        or policy.get("containsUserImagery") is not False
        or policy.get("containsPersonalBodyData") is not False
        or policy.get("approvedDomain") != "avatar_and_garment_only"
    ):
        issues.append(
            _issue(
                "provider_registry_policy_violation",
                "fatal",
                "proposals/provider_registry.json",
                "D0 provider registry cannot permit external APIs, training use or user data.",
            )
        )

    for provider in providers:
        if not isinstance(provider, dict):
            issues.append(
                _issue(
                    "provider_registry_provider_invalid",
                    "fatal",
                    "proposals/provider_registry.json",
                    "Provider entries must be objects.",
                )
            )
            continue
        provider_id = str(provider.get("providerId", ""))
        if provider.get("contractVersion") != registry.get("contractVersion"):
            issues.append(
                _issue(
                    "provider_registry_contract_version_invalid",
                    "fatal",
                    "proposals/provider_registry.json",
                    "Provider contract versions must match the registry contract.",
                    provider_id,
                )
            )
        provider_policy = provider.get("policy", {})
        network_policy = provider.get("networkPolicy", {})
        capabilities = provider.get("capabilities", {})
        declaration = provider.get("capabilityDeclaration", {})
        limits = provider.get("limits", {})
        authority = provider.get("authority", {})
        for block_name, block in [
            ("networkPolicy", network_policy),
            ("capabilities", capabilities),
            ("capabilityDeclaration", declaration),
            ("limits", limits),
            ("authority", authority),
        ]:
            if not isinstance(block, dict):
                issues.append(
                    _issue(
                        "provider_registry_provider_contract_block_invalid",
                        "fatal",
                        "proposals/provider_registry.json",
                        f"Provider {block_name} must be an object.",
                        provider_id,
                    )
                )
                continue
        network_policy = _mapping(network_policy)
        capabilities = _mapping(capabilities)
        declaration = _mapping(declaration)
        limits = _mapping(limits)
        authority = _mapping(authority)
        if not isinstance(provider_policy, dict):
            issues.append(
                _issue(
                    "provider_registry_provider_policy_invalid",
                    "fatal",
                    "proposals/provider_registry.json",
                    "Provider policy entries must be objects.",
                    str(provider.get("providerId", "")),
                )
            )
            continue
        if (
            provider_policy.get("runtimeExternalApis") is not False
            or provider_policy.get("allowTrainingUse") is not False
            or provider_policy.get("acceptsUserImagery") is not False
            or provider_policy.get("containsPersonalBodyData") is not False
            or network_policy.get("runtimeNetworkAccess") is not False
            or network_policy.get("socketAccess") != "denied"
        ):
            issues.append(
                _issue(
                    "provider_registry_provider_policy_violation",
                    "fatal",
                    "proposals/provider_registry.json",
                    (
                        "Provider entries cannot enable external APIs, training use "
                        "or user data in D0."
                    ),
                    provider_id,
                )
            )
        if (
            provider_policy.get("approvedDomain") != "avatar_and_garment_only"
            or provider_policy.get("allowsGenericObjects") is not False
            or declaration.get("supportedDomain") != "avatar_garment_only"
            or declaration.get("canonicalTruthAuthority") is not False
            or "garment_visual_geometry_proposal" not in provider.get("supportedPurposes", [])
            or manifest.get("garmentClass") not in provider.get("supportedGarmentClasses", [])
        ):
            issues.append(
                _issue(
                    "provider_registry_provider_domain_invalid",
                    "fatal",
                    "proposals/provider_registry.json",
                    "Provider entries must be garment/avatar constrained.",
                    provider_id,
                )
            )
        if (
            authority.get("canonicalTruthAuthority") is not False
            or authority.get("requiresCleanAcceptanceGateBeforeCanonical") is not True
        ):
            issues.append(
                _issue(
                    "provider_registry_provider_authority_invalid",
                    "fatal",
                    "proposals/provider_registry.json",
                    "Provider outputs must remain non-canonical until independent gates pass.",
                    provider_id,
                )
            )
        if capabilities.get("producesCleanProposal") is not False:
            issues.append(
                _issue(
                    "provider_registry_provider_clean_authority_invalid",
                    "fatal",
                    "proposals/provider_registry.json",
                    "Phase 5 provider contracts may emit raw proposals but not clean assets.",
                    provider_id,
                )
            )
        if (
            _int_or(limits.get("maxRequestBytes"), -1) < 0
            or _int_or(limits.get("maxOutputBytes"), -1) < 0
            or _int_or(limits.get("maxWallTimeSeconds"), -1) <= 0
            or _int_or(limits.get("maxProcessCount"), -1) <= 0
        ):
            issues.append(
                _issue(
                    "provider_registry_provider_limits_invalid",
                    "fatal",
                    "proposals/provider_registry.json",
                    "Provider contract limits must be finite and bounded.",
                    provider_id,
                )
            )
        if provider_id == "closy.local_open_model_geometry_adapter.v1":
            runtime_requirements = provider.get("runtimeRequirements", {})
            if (
                not isinstance(runtime_requirements, dict)
                or provider.get("status") != "not_run_missing_runtime_or_weights"
                or runtime_requirements.get("weightsAvailable") is not False
                or runtime_requirements.get("ordinaryCiMayDownloadWeights") is not False
                or runtime_requirements.get("ordinaryCiMayInstallExtras") is not False
            ):
                issues.append(
                    _issue(
                        "provider_registry_local_model_runtime_claim_invalid",
                        "fatal",
                        "proposals/provider_registry.json",
                        "Local open-model adapter must remain not-run without authorised runtime.",
                        provider_id,
                    )
                )

    manual_asset_available = manual.get("acceptedForRawProposal") is True
    expected_d0 = [
        ("providerRegistryAvailable", True),
        ("nullProviderAvailable", True),
        ("manualLocalImportAdapterDeclared", True),
        ("manualLocalImportAssetAvailable", manual_asset_available),
        ("localOpenModelAdapterDeclared", True),
        ("localOpenModelExecutionAvailable", False),
        ("providerContractValidationAvailable", True),
        ("providerBakeoffReportAvailable", True),
        ("externalProvidersConfigured", False),
        ("cleanProposalProviderAvailable", False),
    ]
    for key, expected in expected_d0:
        if d0_caps.get(key) is not expected:
            issues.append(
                _issue(
                    "provider_registry_d0_capability_invalid",
                    "fatal",
                    "proposals/provider_registry.json",
                    f"D0 provider capability {key} must be {expected!r}.",
                )
            )

    if manual.get("acceptedForCanonical") is not False:
        issues.append(
            _issue(
                "provider_registry_manual_canonical_invalid",
                "fatal",
                "proposals/provider_registry.json",
                "Manual import candidates are visual proposals and must not be canonical.",
            )
        )
    expected_manual_status = (
        "eligible_raw_visual_proposal" if manual_asset_available else "missing_local_asset"
    )
    if manual.get("status") != expected_manual_status:
        issues.append(
            _issue(
                "provider_registry_manual_status_invalid",
                "fatal",
                "proposals/provider_registry.json",
                "Manual provider status must match the audited local asset state.",
            )
        )
    if selected_provider == "closy.manual_local_glb_import.v1" and not manual_asset_available:
        issues.append(
            _issue(
                "provider_registry_manual_asset_missing",
                "fatal",
                "proposals/provider_registry.json",
                "Manual provider cannot be selected without an accepted local GLB asset.",
            )
        )
    if selected_provider == "closy.manual_local_glb_import.v1":
        manual_provider = next(
            (
                provider
                for provider in providers
                if isinstance(provider, dict)
                and provider.get("providerId") == "closy.manual_local_glb_import.v1"
            ),
            {},
        )
        licence = manual_provider.get("licence", {}) if isinstance(manual_provider, dict) else {}
        if not isinstance(licence, dict) or licence.get("termsReviewed") is not True:
            issues.append(
                _issue(
                    "provider_registry_manual_rights_unreviewed",
                    "fatal",
                    "proposals/provider_registry.json",
                    "Selected manual provider requires explicit asset rights review.",
                )
            )
    if registry_quality is not None:
        expected_quality = {
            "registryId": registry.get("registryId"),
            "selectedProviderId": selected_provider,
            "manualLocalImportAssetAvailable": d0_caps.get("manualLocalImportAssetAvailable"),
            "externalProvidersConfigured": d0_caps.get("externalProvidersConfigured"),
            "cleanProposalProviderAvailable": d0_caps.get("cleanProposalProviderAvailable"),
            "manualImportStatus": manual.get("status"),
            "manualImportFailureReason": manual.get("failureReason"),
        }
        for key, expected in expected_quality.items():
            if registry_quality.get(key) != expected:
                issues.append(
                    _issue(
                        "provider_registry_quality_mismatch",
                        "fatal",
                        "reports/provider_registry_quality.json",
                        f"Provider registry quality field {key} must match the registry.",
                    )
                )

    caps = manifest.get("capabilities", {})
    if isinstance(caps, dict):
        expected_manifest = [
            ("geometryProviderRegistryAvailable", True),
            ("providerContractValidationAvailable", True),
            ("providerBakeoffReportAvailable", True),
            ("manualGeometryImportAdapterDeclared", True),
            ("manualGeometryImportAssetAvailable", manual_asset_available),
            ("localOpenModelAdapterDeclared", True),
            ("localOpenModelExecutionAvailable", False),
            ("externalGeometryProvidersConfigured", False),
            ("cleanGeometryProposalAvailable", False),
        ]
        for key, expected in expected_manifest:
            if caps.get(key) is not expected:
                issues.append(
                    _issue(
                        "provider_registry_manifest_capability_invalid",
                        "fatal",
                        "manifest.json",
                        f"Manifest capability {key} must be {expected!r}.",
                    )
                )

    future_slots = registry.get("futureProviderSlots", [])
    if isinstance(future_slots, list):
        for slot in future_slots:
            if not isinstance(slot, dict):
                continue
            if not str(slot.get("status", "")).startswith("unconfigured_"):
                issues.append(
                    _issue(
                        "provider_registry_future_slot_invalid",
                        "fatal",
                        "proposals/provider_registry.json",
                        "Future provider slots must remain explicitly unconfigured in D0.",
                        str(slot.get("providerId", "")),
                    )
                )

    if _contains_nonfinite(registry):
        issues.append(
            _issue(
                "provider_registry_nonfinite_numeric_value",
                "fatal",
                "proposals/provider_registry.json",
                "Provider registry must not contain NaN or Infinity.",
            )
        )


def _validate_provider_bakeoff(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    registry = _read_required_json(package_dir, "proposals/provider_registry.json", issues)
    proposal = _read_required_json(package_dir, "proposals/raw_geometry_proposal.json", issues)
    topology = _read_required_json(package_dir, "reports/raw_geometry_topology.json", issues)
    bakeoff = _read_required_json(package_dir, "reports/provider_bakeoff.json", issues)
    if registry is None or proposal is None or topology is None or bakeoff is None:
        return
    if bakeoff.get("garmentId") != manifest.get("garmentId"):
        issues.append(
            _issue(
                "provider_bakeoff_garment_mismatch",
                "fatal",
                "reports/provider_bakeoff.json",
                "Provider bake-off report must reference the package garment ID.",
            )
        )
    if bakeoff.get("garmentClass") != manifest.get("garmentClass"):
        issues.append(
            _issue(
                "provider_bakeoff_class_mismatch",
                "fatal",
                "reports/provider_bakeoff.json",
                "Provider bake-off report must reference the package garment class.",
            )
        )
    if bakeoff.get("status") != "completed_d0_contract_only_clean_rejected":
        issues.append(
            _issue(
                "provider_bakeoff_status_invalid",
                "fatal",
                "reports/provider_bakeoff.json",
                "Provider bake-off must remain a D0 contract-only clean-rejected report.",
            )
        )
    expected_hashes = [
        (
            "sourceProviderRegistryHash",
            _nested_string(registry, ["integrity", "providerRegistryHash"], ""),
            "provider_bakeoff_registry_hash_mismatch",
        ),
        (
            "sourceRawProposalHash",
            _nested_string(proposal, ["integrity", "geometryProposalHash"], ""),
            "provider_bakeoff_proposal_hash_mismatch",
        ),
        (
            "sourceRawTopologyReportHash",
            _nested_string(topology, ["integrity", "rawGeometryTopologyReportHash"], ""),
            "provider_bakeoff_topology_hash_mismatch",
        ),
    ]
    for field, expected_hash, code in expected_hashes:
        if bakeoff.get(field) != expected_hash:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "reports/provider_bakeoff.json",
                    f"Provider bake-off {field} must match its source artifact.",
                )
            )
    if _nested_string(bakeoff, ["integrity", "providerBakeoffHash"], "") != (
        hash_provider_bakeoff_report(bakeoff)
    ):
        issues.append(
            _issue(
                "provider_bakeoff_hash_mismatch",
                "fatal",
                "reports/provider_bakeoff.json",
                "Provider bake-off hash must match its canonical payload.",
            )
        )
    provider_results = bakeoff.get("providerResults", [])
    if not isinstance(provider_results, list) or not provider_results:
        issues.append(
            _issue(
                "provider_bakeoff_result_list_invalid",
                "fatal",
                "reports/provider_bakeoff.json",
                "Provider bake-off must include one result per registry provider.",
            )
        )
        provider_results = []
    result_ids = {
        str(result.get("providerId", "")) for result in provider_results if isinstance(result, dict)
    }
    registry_ids = {
        str(provider.get("providerId", ""))
        for provider in registry.get("providers", [])
        if isinstance(provider, dict)
    }
    if result_ids != registry_ids:
        issues.append(
            _issue(
                "provider_bakeoff_provider_set_mismatch",
                "fatal",
                "reports/provider_bakeoff.json",
                "Provider bake-off results must match the provider registry provider IDs.",
            )
        )
    selected_provider = str(registry.get("selectedProviderId", ""))
    selected_results = [
        result
        for result in provider_results
        if isinstance(result, dict) and result.get("providerId") == selected_provider
    ]
    if len(selected_results) != 1:
        issues.append(
            _issue(
                "provider_bakeoff_selected_result_invalid",
                "fatal",
                "reports/provider_bakeoff.json",
                "Provider bake-off must include exactly one selected provider result.",
            )
        )
    for result in provider_results:
        if not isinstance(result, dict):
            continue
        provider_id = str(result.get("providerId", ""))
        if result.get("networkAccessObserved") is not False:
            issues.append(
                _issue(
                    "provider_bakeoff_network_policy_violation",
                    "fatal",
                    "reports/provider_bakeoff.json",
                    "Provider bake-off cannot record network access in D0.",
                    provider_id,
                )
            )
        if result.get("acceptedForCanonical") is not False:
            issues.append(
                _issue(
                    "provider_bakeoff_canonical_acceptance_invalid",
                    "fatal",
                    "reports/provider_bakeoff.json",
                    "Provider bake-off cannot grant canonical acceptance.",
                    provider_id,
                )
            )
        cleanup_effort = result.get("cleanupEffortStatus")
        expected_cleanup_efforts = {
            "not_run_no_raw_geometry",
            "cleanup_required_before_clean_or_canonical_use",
            "not_selected_cleanup_not_assessed",
            "no_cleanup_required_for_visual_reference",
        }
        if cleanup_effort not in expected_cleanup_efforts:
            issues.append(
                _issue(
                    "provider_bakeoff_cleanup_effort_invalid",
                    "fatal",
                    "reports/provider_bakeoff.json",
                    "Provider bake-off must record a bounded cleanup-effort status.",
                    provider_id,
                )
            )
        if (
            provider_id == "closy.local_open_model_geometry_adapter.v1"
            and result.get("executionStatus") != "not_run_missing_runtime_or_weights"
        ):
            issues.append(
                _issue(
                    "provider_bakeoff_local_model_status_invalid",
                    "fatal",
                    "reports/provider_bakeoff.json",
                    "Local open-model provider must remain not-run without runtime/weights.",
                    provider_id,
                )
            )
        if provider_id == selected_provider and result.get("executionStatus") != (
            "completed_manual_fixture_import"
        ):
            issues.append(
                _issue(
                    "provider_bakeoff_selected_execution_invalid",
                    "fatal",
                    "reports/provider_bakeoff.json",
                    "Selected demo provider must match the completed manual fixture invocation.",
                    provider_id,
                )
            )
    aggregate = bakeoff.get("aggregate", {})
    if not isinstance(aggregate, dict):
        issues.append(
            _issue(
                "provider_bakeoff_aggregate_invalid",
                "fatal",
                "reports/provider_bakeoff.json",
                "Provider bake-off aggregate must be an object.",
            )
        )
        aggregate = {}
    expected_provider_count = len(provider_results)
    executed_provider_count = sum(
        1
        for result in provider_results
        if isinstance(result, dict)
        and str(result.get("executionStatus", "")).startswith("completed")
    )
    not_run_provider_count = sum(
        1
        for result in provider_results
        if isinstance(result, dict) and str(result.get("executionStatus", "")).startswith("not_run")
    )
    if (
        _int_or(aggregate.get("providerCount"), -1) != expected_provider_count
        or _int_or(aggregate.get("executedProviderCount"), -1) != executed_provider_count
        or _int_or(aggregate.get("notRunProviderCount"), -1) != not_run_provider_count
        or _int_or(aggregate.get("canonicalAcceptedProviderCount"), -1) != 0
        or aggregate.get("bestAvailableProviderId") != selected_provider
    ):
        issues.append(
            _issue(
                "provider_bakeoff_aggregate_invalid",
                "fatal",
                "reports/provider_bakeoff.json",
                "Provider bake-off aggregate is stale or overclaims provider acceptance.",
            )
        )
    policy = bakeoff.get("policy", {})
    if not isinstance(policy, dict) or (
        policy.get("allowExternalApis") is not False
        or policy.get("allowTrainingUse") is not False
        or policy.get("containsUserImagery") is not False
        or policy.get("providerOutputMayBecomeCanonicalWithoutGate") is not False
    ):
        issues.append(
            _issue(
                "provider_bakeoff_policy_violation",
                "fatal",
                "reports/provider_bakeoff.json",
                "Provider bake-off must preserve D0 provider and canonicality boundaries.",
            )
        )
    caps = manifest.get("capabilities", {})
    if isinstance(caps, dict):
        for key, expected in [
            ("providerBakeoffReportAvailable", True),
            ("localOpenModelExecutionAvailable", False),
            ("externalGeometryProvidersConfigured", False),
            ("cleanGeometryProposalAvailable", False),
        ]:
            if caps.get(key) is not expected:
                issues.append(
                    _issue(
                        "provider_bakeoff_manifest_capability_invalid",
                        "fatal",
                        "manifest.json",
                        f"Manifest capability {key} must be {expected!r}.",
                    )
                )
    if _contains_nonfinite(bakeoff):
        issues.append(
            _issue(
                "provider_bakeoff_nonfinite_numeric_value",
                "fatal",
                "reports/provider_bakeoff.json",
                "Provider bake-off report must not contain NaN or Infinity.",
            )
        )


def _validate_clean_geometry_proposal(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    raw_proposal = _read_required_json(package_dir, "proposals/raw_geometry_proposal.json", issues)
    provider_registry = _read_required_json(package_dir, "proposals/provider_registry.json", issues)
    raw_topology = _read_required_json(package_dir, "reports/raw_geometry_topology.json", issues)
    cleanup_plan = _read_required_json(package_dir, "reports/geometry_cleanup_plan.json", issues)
    cleanup_result = _read_required_json(
        package_dir, "reports/geometry_cleanup_result.json", issues
    )
    semantic_transfer = _read_required_json(
        package_dir, "reports/geometry_semantic_transfer.json", issues
    )
    binding_candidate = _read_required_json(
        package_dir, "reports/geometry_binding_candidate.json", issues
    )
    binding_validation = _read_required_json(
        package_dir, "reports/geometry_binding_validation.json", issues
    )
    repair_plan = _read_required_json(
        package_dir, "reports/geometry_repair_retopology_plan.json", issues
    )
    repair_result = _read_required_json(package_dir, "reports/geometry_repair_result.json", issues)
    runtime_binding_result = _read_required_json(
        package_dir, "reports/geometry_runtime_binding_result.json", issues
    )
    material_uv_transfer = _read_required_json(
        package_dir, "reports/geometry_material_uv_transfer.json", issues
    )
    visual_shell_review = _read_required_json(
        package_dir, "reports/geometry_visual_shell_review.json", issues
    )
    clean_acceptance_gate = _read_required_json(
        package_dir, "reports/geometry_clean_acceptance_gate.json", issues
    )
    clean_proposal = _read_required_json(
        package_dir, "proposals/clean_geometry_proposal.json", issues
    )
    clean_quality = _read_required_json(
        package_dir, "reports/clean_geometry_proposal_quality.json", issues
    )
    if (
        raw_proposal is None
        or provider_registry is None
        or raw_topology is None
        or cleanup_plan is None
        or cleanup_result is None
        or semantic_transfer is None
        or binding_candidate is None
        or binding_validation is None
        or repair_plan is None
        or repair_result is None
        or runtime_binding_result is None
        or material_uv_transfer is None
        or visual_shell_review is None
        or clean_acceptance_gate is None
        or clean_proposal is None
    ):
        return

    if clean_proposal.get("garmentId") != manifest.get("garmentId"):
        issues.append(
            _issue(
                "clean_geometry_proposal_garment_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean geometry proposal must reference the package garment ID.",
            )
        )
    if clean_proposal.get("garmentClass") != manifest.get("garmentClass"):
        issues.append(
            _issue(
                "clean_geometry_proposal_class_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean geometry proposal must reference the package garment class.",
            )
        )

    expected_hashes = [
        (
            "sourceRawProposalHash",
            _nested_string(raw_proposal, ["integrity", "geometryProposalHash"], ""),
            "clean_geometry_proposal_raw_hash_mismatch",
        ),
        (
            "sourceProviderRegistryHash",
            _nested_string(provider_registry, ["integrity", "providerRegistryHash"], ""),
            "clean_geometry_proposal_registry_hash_mismatch",
        ),
        (
            "sourceRawTopologyReportHash",
            _nested_string(raw_topology, ["integrity", "rawGeometryTopologyReportHash"], ""),
            "clean_geometry_proposal_topology_hash_mismatch",
        ),
        (
            "sourceGeometryCleanupPlanHash",
            _nested_string(cleanup_plan, ["integrity", "geometryCleanupPlanHash"], ""),
            "clean_geometry_proposal_cleanup_plan_hash_mismatch",
        ),
        (
            "sourceGeometryCleanupResultHash",
            _nested_string(cleanup_result, ["integrity", "geometryCleanupResultHash"], ""),
            "clean_geometry_proposal_cleanup_result_hash_mismatch",
        ),
        (
            "sourceGeometrySemanticTransferHash",
            _nested_string(semantic_transfer, ["integrity", "geometrySemanticTransferHash"], ""),
            "clean_geometry_proposal_semantic_transfer_hash_mismatch",
        ),
        (
            "sourceGeometryBindingCandidateHash",
            _nested_string(binding_candidate, ["integrity", "geometryBindingCandidateHash"], ""),
            "clean_geometry_proposal_binding_candidate_hash_mismatch",
        ),
        (
            "sourceGeometryBindingValidationHash",
            _nested_string(binding_validation, ["integrity", "geometryBindingValidationHash"], ""),
            "clean_geometry_proposal_binding_validation_hash_mismatch",
        ),
        (
            "sourceGeometryRepairRetopologyPlanHash",
            _nested_string(repair_plan, ["integrity", "geometryRepairRetopologyPlanHash"], ""),
            "clean_geometry_proposal_repair_retopology_plan_hash_mismatch",
        ),
        (
            "sourceGeometryRepairResultHash",
            _nested_string(repair_result, ["integrity", "geometryRepairResultHash"], ""),
            "clean_geometry_proposal_repair_result_hash_mismatch",
        ),
        (
            "sourceGeometryRuntimeBindingResultHash",
            _nested_string(
                runtime_binding_result,
                ["integrity", "geometryRuntimeBindingResultHash"],
                "",
            ),
            "clean_geometry_proposal_runtime_binding_result_hash_mismatch",
        ),
        (
            "sourceGeometryMaterialUvTransferHash",
            _nested_string(
                material_uv_transfer,
                ["integrity", "geometryMaterialUvTransferHash"],
                "",
            ),
            "clean_geometry_proposal_material_uv_transfer_hash_mismatch",
        ),
        (
            "sourceGeometryVisualShellReviewHash",
            _nested_string(
                visual_shell_review,
                ["integrity", "geometryVisualShellReviewHash"],
                "",
            ),
            "clean_geometry_proposal_visual_shell_review_hash_mismatch",
        ),
        (
            "sourceGeometryCleanAcceptanceGateHash",
            _nested_string(
                clean_acceptance_gate,
                ["integrity", "geometryCleanAcceptanceGateHash"],
                "",
            ),
            "clean_geometry_proposal_clean_acceptance_gate_hash_mismatch",
        ),
    ]
    for field, expected_hash, code in expected_hashes:
        if clean_proposal.get(field) != expected_hash:
            issues.append(
                _issue(
                    code,
                    "fatal",
                    "proposals/clean_geometry_proposal.json",
                    f"Clean geometry proposal {field} must match its source artifact.",
                )
            )
    if clean_proposal.get("sourceRawProposalId") != raw_proposal.get("proposalId"):
        issues.append(
            _issue(
                "clean_geometry_proposal_raw_source_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean geometry proposal must reference the raw proposal ID.",
            )
        )
    if clean_proposal.get("sourceProviderRegistryId") != provider_registry.get("registryId"):
        issues.append(
            _issue(
                "clean_geometry_proposal_registry_source_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean geometry proposal must reference the provider registry ID.",
            )
        )
    if clean_proposal.get("sourceRawTopologyReportId") != raw_topology.get("reportId"):
        issues.append(
            _issue(
                "clean_geometry_proposal_topology_source_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean geometry proposal must reference the raw topology report ID.",
            )
        )
    if clean_proposal.get("sourceGeometryCleanupPlanId") != cleanup_plan.get("reportId"):
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_plan_source_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean geometry proposal must reference the cleanup plan ID.",
            )
        )
    if clean_proposal.get("sourceGeometryCleanupResultId") != cleanup_result.get("reportId"):
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_result_source_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean geometry proposal must reference the cleanup result ID.",
            )
        )
    if clean_proposal.get("sourceGeometrySemanticTransferId") != semantic_transfer.get("reportId"):
        issues.append(
            _issue(
                "clean_geometry_proposal_semantic_transfer_source_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean geometry proposal must reference the semantic transfer report ID.",
            )
        )
    if clean_proposal.get("sourceGeometryBindingCandidateId") != binding_candidate.get("reportId"):
        issues.append(
            _issue(
                "clean_geometry_proposal_binding_candidate_source_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean geometry proposal must reference the binding candidate report ID.",
            )
        )
    if clean_proposal.get("sourceGeometryBindingValidationId") != binding_validation.get(
        "reportId"
    ):
        issues.append(
            _issue(
                "clean_geometry_proposal_binding_validation_source_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean geometry proposal must reference the binding validation report ID.",
            )
        )
    if clean_proposal.get("sourceGeometryRepairRetopologyPlanId") != repair_plan.get("reportId"):
        issues.append(
            _issue(
                "clean_geometry_proposal_repair_retopology_plan_source_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean geometry proposal must reference the repair/retopology plan ID.",
            )
        )
    if clean_proposal.get("sourceGeometryRepairResultId") != repair_result.get("reportId"):
        issues.append(
            _issue(
                "clean_geometry_proposal_repair_result_source_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean geometry proposal must reference the repair result ID.",
            )
        )
    if clean_proposal.get("sourceGeometryRuntimeBindingResultId") != runtime_binding_result.get(
        "reportId"
    ):
        issues.append(
            _issue(
                "clean_geometry_proposal_runtime_binding_result_source_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean geometry proposal must reference the runtime binding result ID.",
            )
        )
    if clean_proposal.get("sourceGeometryMaterialUvTransferId") != material_uv_transfer.get(
        "reportId"
    ):
        issues.append(
            _issue(
                "clean_geometry_proposal_material_uv_transfer_source_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean geometry proposal must reference the material/UV transfer report ID.",
            )
        )
    if clean_proposal.get("sourceGeometryVisualShellReviewId") != visual_shell_review.get(
        "reportId"
    ):
        issues.append(
            _issue(
                "clean_geometry_proposal_visual_shell_review_source_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean geometry proposal must reference the visual/shell review report ID.",
            )
        )
    if clean_proposal.get("sourceGeometryCleanAcceptanceGateId") != clean_acceptance_gate.get(
        "reportId"
    ):
        issues.append(
            _issue(
                "clean_geometry_proposal_clean_acceptance_gate_source_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean geometry proposal must reference the clean acceptance gate ID.",
            )
        )

    if _nested_string(clean_proposal, ["integrity", "cleanGeometryProposalHash"], "") != (
        hash_clean_geometry_proposal(clean_proposal)
    ):
        issues.append(
            _issue(
                "clean_geometry_proposal_hash_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean geometry proposal hash must match its canonical payload.",
            )
        )

    raw = clean_proposal.get("rawProposal", {})
    cleanup = clean_proposal.get("cleanupPipeline", {})
    clean = clean_proposal.get("cleanProposal", {})
    audit = clean_proposal.get("cleanGeometryAudit", {})
    canonicalization = clean_proposal.get("canonicalization", {})
    quality = clean_proposal.get("quality", {})
    policy = clean_proposal.get("policy", {})
    for name, block in [
        ("rawProposal", raw),
        ("cleanupPipeline", cleanup),
        ("cleanProposal", clean),
        ("cleanGeometryAudit", audit),
        ("canonicalization", canonicalization),
        ("quality", quality),
        ("policy", policy),
    ]:
        if not isinstance(block, dict):
            issues.append(
                _issue(
                    "clean_geometry_proposal_block_invalid",
                    "fatal",
                    "proposals/clean_geometry_proposal.json",
                    f"Clean geometry proposal {name} block must be an object.",
                )
            )
            return

    if raw.get("assetPath") != _nested_string(raw_proposal, ["rawProposal", "assetPath"], ""):
        issues.append(
            _issue(
                "clean_geometry_proposal_raw_asset_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal raw asset reference must mirror the raw proposal.",
            )
        )
    if raw.get("sourceAssetHash") != raw_proposal.get("rawProposal", {}).get("sourceAssetHash"):
        issues.append(
            _issue(
                "clean_geometry_proposal_raw_asset_hash_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal raw asset hash must mirror the raw proposal.",
            )
        )

    if (
        quality.get("status") != "rejected"
        or clean.get("available") is not False
        or audit.get("meshAvailable") is not False
        or _int_or(audit.get("meshCount"), -1) != 0
        or _int_or(audit.get("triangleEstimate"), -1) != 0
    ):
        issues.append(
            _issue(
                "clean_geometry_proposal_availability_invalid",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "D0 clean geometry proposal must remain rejected and unavailable.",
            )
        )

    if (
        quality.get("acceptedForCanonical") is not False
        or quality.get("acceptedForSimulation") is not False
        or quality.get("acceptedForRuntimeRender") is not False
        or clean.get("acceptedForCanonical") is not False
        or clean.get("acceptedForSimulation") is not False
        or clean.get("acceptedForRuntimeRender") is not False
        or canonicalization.get("canonicalUseAllowed") is not False
    ):
        issues.append(
            _issue(
                "clean_geometry_proposal_canonical_acceptance_invalid",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                (
                    "Rejected clean proposals cannot be accepted for canonical, "
                    "simulation or runtime use."
                ),
            )
        )

    if cleanup.get("cleanupRun") != cleanup_result.get("execution", {}).get("cleanupRun"):
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_state_invalid",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal cleanupRun must mirror the cleanup result.",
            )
        )
    semantic_execution = semantic_transfer.get("execution", {})
    if cleanup.get("semanticTransferRun") != semantic_execution.get("semanticTransferRun"):
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_state_invalid",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal semanticTransferRun must mirror the semantic transfer report.",
            )
        )
    if cleanup.get("boundaryClassificationRun") != semantic_execution.get(
        "boundaryClassificationRun"
    ):
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_state_invalid",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                (
                    "Clean proposal boundaryClassificationRun must mirror the semantic "
                    "transfer report."
                ),
            )
        )
    binding_execution = binding_candidate.get("execution", {})
    if cleanup.get("candidateBindingRun") != binding_execution.get("candidateBindingRun"):
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_state_invalid",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal candidateBindingRun must mirror the binding candidate report.",
            )
        )
    validation_execution = binding_validation.get("execution", {})
    repair_result_execution = repair_result.get("execution", {})
    runtime_binding_result_execution = runtime_binding_result.get("execution", {})
    if cleanup.get("simulationBindingRun") != runtime_binding_result_execution.get(
        "runtimeBindingAccepted"
    ):
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_state_invalid",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal simulationBindingRun must mirror runtime binding acceptance.",
            )
        )
    if cleanup.get("deformationValidationRun") != validation_execution.get(
        "deformationValidationRun"
    ):
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_state_invalid",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                (
                    "Clean proposal deformationValidationRun must mirror the binding "
                    "validation report."
                ),
            )
        )
    if cleanup.get("runtimeBindingResultGenerated") is not True:
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_state_invalid",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal runtimeBindingResultGenerated must be true.",
            )
        )
    if cleanup.get("runtimeBindingResultGenerated") != runtime_binding_result_execution.get(
        "runtimeBindingResultGenerated"
    ):
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_state_invalid",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                (
                    "Clean proposal runtimeBindingResultGenerated must mirror the runtime "
                    "binding result."
                ),
            )
        )
    for key in [
        "retopologyRun",
        "seamSplitRun",
        "componentStitchingRun",
        "normalContinuityValidationRun",
        "tangentContinuityValidationRun",
        "runtimeBindingWritten",
        "runtimeBindingAccepted",
    ]:
        if cleanup.get(key) != runtime_binding_result_execution.get(key):
            issues.append(
                _issue(
                    "clean_geometry_proposal_cleanup_state_invalid",
                    "fatal",
                    "proposals/clean_geometry_proposal.json",
                    f"Clean proposal {key} must mirror the runtime binding result.",
                )
            )
    clean_gate_execution = clean_acceptance_gate.get("execution", {})
    material_transfer_execution = material_uv_transfer.get("execution", {})
    material_transfer_readiness = material_uv_transfer.get("readiness", {})
    material_transfer_aggregate = material_uv_transfer.get("aggregate", {})
    visual_shell_execution = visual_shell_review.get("execution", {})
    visual_shell_readiness = visual_shell_review.get("readiness", {})
    visual_shell_aggregate = visual_shell_review.get("aggregate", {})
    if cleanup.get("materialUvTransferReportGenerated") is not True:
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_state_invalid",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal materialUvTransferReportGenerated must be true.",
            )
        )
    if cleanup.get("uvTransferRun") != material_transfer_execution.get("uvTransferRun"):
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_state_invalid",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal uvTransferRun must mirror the material/UV transfer report.",
            )
        )
    if cleanup.get("materialTransferRun") != material_transfer_execution.get("materialTransferRun"):
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_state_invalid",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal materialTransferRun must mirror the material/UV transfer report.",
            )
        )
    if cleanup.get("materialTransferAccepted") != material_transfer_readiness.get(
        "acceptedForMaterialPreview"
    ):
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_state_invalid",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                (
                    "Clean proposal materialTransferAccepted must mirror material-preview "
                    "readiness."
                ),
            )
        )
    if cleanup.get("materialTransferRun") != clean_gate_execution.get("materialTransferRun"):
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_state_invalid",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal materialTransferRun must mirror the clean acceptance gate.",
            )
        )
    if cleanup.get("visualShellReviewGenerated") is not True:
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_state_invalid",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal visualShellReviewGenerated must be true.",
            )
        )
    expected_visual_flags = {
        "visualFidelityReviewRun": visual_shell_execution.get("visualFidelityReviewRun"),
        "providerVisualFidelityAccepted": visual_shell_readiness.get("acceptedForVisualFidelity"),
        "representationSilhouetteComparisonRun": visual_shell_execution.get(
            "representationSilhouetteComparisonRun"
        ),
        "representationSilhouetteAccepted": visual_shell_readiness.get(
            "representationSilhouetteAccepted"
        ),
        "sourceImageVisualComparisonRun": visual_shell_execution.get(
            "sourceImageVisualComparisonRun"
        ),
        "sourceImageVisualFidelityAccepted": visual_shell_readiness.get(
            "sourceImageVisualFidelityAccepted"
        ),
        "providerAppearanceComparisonRun": visual_shell_execution.get(
            "providerAppearanceComparisonRun"
        ),
        "providerAppearanceAccepted": visual_shell_readiness.get("providerAppearanceAccepted"),
        "stitchGraphConnectivityCheckRun": visual_shell_execution.get(
            "stitchGraphConnectivityCheckRun"
        ),
        "stitchGraphConnectable": visual_shell_readiness.get("stitchGraphConnectable"),
        "meshStitchOrWeldExecutionRun": visual_shell_execution.get("meshStitchOrWeldExecutionRun"),
        "meshStitchOrWeldProven": visual_shell_readiness.get("meshStitchOrWeldProven"),
        "singleShellWeldProofRun": visual_shell_execution.get("singleShellWeldProofRun"),
        "singleShellWeldProven": visual_shell_readiness.get("singleShellWeldProven"),
    }
    for key, expected in expected_visual_flags.items():
        if cleanup.get(key) != expected:
            issues.append(
                _issue(
                    "clean_geometry_proposal_cleanup_state_invalid",
                    "fatal",
                    "proposals/clean_geometry_proposal.json",
                    f"Clean proposal {key} must mirror the visual/shell review report.",
                )
            )
    for key in [
        "visualFidelityReviewRun",
        "singleShellWeldProofRun",
        "meshStitchOrWeldExecutionRun",
    ]:
        if cleanup.get(key) != clean_gate_execution.get(key):
            issues.append(
                _issue(
                    "clean_geometry_proposal_cleanup_state_invalid",
                    "fatal",
                    "proposals/clean_geometry_proposal.json",
                    f"Clean proposal {key} must mirror the clean acceptance gate.",
                )
            )
    if cleanup.get("cleanAcceptanceGateGenerated") is not True:
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_state_invalid",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal cleanAcceptanceGateGenerated must be true.",
            )
        )
    if cleanup.get("cleanAcceptanceGateRun") != clean_gate_execution.get("cleanAcceptanceGateRun"):
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_state_invalid",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal cleanAcceptanceGateRun must mirror the clean acceptance gate.",
            )
        )
    if cleanup.get("cleanAcceptanceGateAccepted") != clean_acceptance_gate.get("readiness", {}).get(
        "acceptedForCleanProposal"
    ):
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_state_invalid",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                (
                    "Clean proposal cleanAcceptanceGateAccepted must mirror the clean "
                    "acceptance gate."
                ),
            )
        )
    if cleanup.get("deformationReprojectionRun") != repair_result_execution.get(
        "deformationReprojectionRun"
    ):
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_state_invalid",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal deformationReprojectionRun must mirror the repair result.",
            )
        )
    for key in [
        "repairRun",
    ]:
        if cleanup.get(key) is not False:
            issues.append(
                _issue(
                    "clean_geometry_proposal_cleanup_state_invalid",
                    "fatal",
                    "proposals/clean_geometry_proposal.json",
                    f"Clean proposal field cleanupPipeline.{key} must stay false in D0.",
                )
            )

    if (
        cleanup.get("topologyDiagnosticsRun") is not True
        or cleanup.get("cleanupPlanGenerated") is not True
        or cleanup.get("cleanupResultGenerated") is not True
        or cleanup.get("semanticTransferReportGenerated") is not True
        or cleanup.get("bindingCandidateReportGenerated") is not True
        or cleanup.get("bindingValidationReportGenerated") is not True
        or cleanup.get("repairRetopologyPlanGenerated") is not True
        or cleanup.get("partialRepairResultGenerated") is not True
        or cleanup.get("runtimeBindingResultGenerated") is not True
        or cleanup.get("materialUvTransferReportGenerated") is not True
        or cleanup.get("visualShellReviewGenerated") is not True
        or cleanup.get("retopologyRun") is not True
        or cleanup.get("seamSplitRun") is not True
        or cleanup.get("componentStitchingRun") is not True
        or cleanup.get("normalContinuityValidationRun") is not True
        or cleanup.get("tangentContinuityValidationRun") is not True
        or cleanup.get("runtimeBindingWritten") is not True
        or cleanup.get("runtimeBindingAccepted") is not True
        or cleanup.get("cleanAcceptanceGateGenerated") is not True
        or cleanup.get("cleanAcceptanceGateRun") is not True
        or cleanup.get("cleanAcceptanceGateAccepted") is not False
        or cleanup.get("uvTransferRun") is not True
        or cleanup.get("materialTransferRun") is not True
        or cleanup.get("materialTransferAccepted") is not True
        or cleanup.get("representationSilhouetteComparisonRun") is not True
        or cleanup.get("representationSilhouetteAccepted") is not True
        or cleanup.get("visualFidelityReviewRun") is not False
        or cleanup.get("sourceImageVisualComparisonRun") is not False
        or cleanup.get("providerAppearanceComparisonRun") is not False
        or cleanup.get("stitchGraphConnectivityCheckRun") is not True
        or cleanup.get("stitchGraphConnectable") is not True
        or cleanup.get("singleShellWeldProofRun") is not False
        or cleanup.get("meshStitchOrWeldExecutionRun")
        is not visual_shell_execution.get("meshStitchOrWeldExecutionRun")
        or cleanup.get("connectedComponentAnalysisRun") is not True
        or cleanup.get("nonManifoldAnalysisRun") is not True
    ):
        issues.append(
            _issue(
                "clean_geometry_proposal_topology_state_invalid",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                (
                    "Clean proposal must link completed raw topology, cleanup plan, cleanup "
                    "result, semantic transfer, binding candidate, binding validation and "
                    "repair/retopology execution evidence."
                ),
            )
        )
    topology_block = raw_topology.get("topology", {})
    if isinstance(topology_block, dict):
        expected_topology_fields = {
            "connectedComponentCount": topology_block.get("componentCount"),
            "nonManifoldEdgeCount": topology_block.get("nonManifoldEdgeCount"),
            "degenerateTriangleCount": topology_block.get("degenerateTriangleCount"),
            "rawTopologyManifoldStatus": topology_block.get("manifoldStatus"),
        }
        for key, expected in expected_topology_fields.items():
            if audit.get(key) != expected:
                issues.append(
                    _issue(
                        "clean_geometry_proposal_topology_mismatch",
                        "fatal",
                        "proposals/clean_geometry_proposal.json",
                        f"Clean proposal topology audit field {key} is stale.",
                    )
                )

    readiness = cleanup_plan.get("readiness", {})
    if isinstance(readiness, dict) and audit.get("cleanupPlanStatus") != readiness.get("status"):
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_plan_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal cleanup plan status is stale.",
            )
        )
    result_readiness = cleanup_result.get("readiness", {})
    if isinstance(result_readiness, dict) and audit.get(
        "cleanupResultStatus"
    ) != result_readiness.get("status"):
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_result_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal cleanup result status is stale.",
            )
        )
    result_output = cleanup_result.get("outputAsset", {})
    result_after = cleanup_result.get("topologyAfter", {})
    if isinstance(result_output, dict):
        expected_output_fields = {
            "cleanupPreviewAssetPath": result_output.get("path"),
            "cleanupPreviewAssetHash": result_output.get("sourceAssetHash"),
        }
        for key, expected in expected_output_fields.items():
            if audit.get(key) != expected:
                issues.append(
                    _issue(
                        "clean_geometry_proposal_cleanup_result_mismatch",
                        "fatal",
                        "proposals/clean_geometry_proposal.json",
                        f"Clean proposal cleanup result field {key} is stale.",
                    )
                )
    if isinstance(result_after, dict):
        expected_post_fields = {
            "postCleanupComponentCount": result_after.get("componentCount"),
            "postCleanupBoundaryEdgeCount": result_after.get("boundaryEdgeCount"),
            "postCleanupDuplicatePositionCount": result_after.get("duplicatePositionCount"),
        }
        for key, expected in expected_post_fields.items():
            if audit.get(key) != expected:
                issues.append(
                    _issue(
                        "clean_geometry_proposal_cleanup_result_mismatch",
                        "fatal",
                        "proposals/clean_geometry_proposal.json",
                        f"Clean proposal cleanup result field {key} is stale.",
                    )
                )

    semantic_readiness = semantic_transfer.get("readiness", {})
    if isinstance(semantic_readiness, dict) and audit.get(
        "semanticTransferStatus"
    ) != semantic_readiness.get("status"):
        issues.append(
            _issue(
                "clean_geometry_proposal_semantic_transfer_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal semantic transfer status is stale.",
            )
        )
    semantic_aggregate = semantic_transfer.get("aggregate", {})
    if isinstance(semantic_aggregate, dict):
        expected_semantic_fields = {
            "transferredPanelCount": semantic_aggregate.get("transferredPanelCount"),
            "classifiedBoundaryEdgeCount": semantic_aggregate.get("classifiedBoundaryEdgeCount"),
            "unclassifiedBoundaryEdgeCount": semantic_aggregate.get(
                "unclassifiedBoundaryEdgeCount"
            ),
            "ambiguousBoundaryEdgeCount": semantic_aggregate.get("ambiguousBoundaryEdgeCount"),
        }
        for key, expected in expected_semantic_fields.items():
            if audit.get(key) != expected:
                issues.append(
                    _issue(
                        "clean_geometry_proposal_semantic_transfer_mismatch",
                        "fatal",
                        "proposals/clean_geometry_proposal.json",
                        f"Clean proposal semantic transfer field {key} is stale.",
                    )
                )

    binding_readiness = binding_candidate.get("readiness", {})
    if isinstance(binding_readiness, dict) and audit.get(
        "bindingCandidateStatus"
    ) != binding_readiness.get("status"):
        issues.append(
            _issue(
                "clean_geometry_proposal_binding_candidate_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal binding candidate status is stale.",
            )
        )
    binding_aggregate = binding_candidate.get("aggregate", {})
    if isinstance(binding_aggregate, dict):
        expected_binding_fields = {
            "bindingCandidateMappedVertexCount": binding_aggregate.get("mappedVertexCount"),
            "bindingCandidateUnmappedVertexCount": binding_aggregate.get("unmappedVertexCount"),
            "bindingCandidateCompleteness": binding_aggregate.get("candidateCompleteness"),
        }
        for key, expected in expected_binding_fields.items():
            if audit.get(key) != expected:
                issues.append(
                    _issue(
                        "clean_geometry_proposal_binding_candidate_mismatch",
                        "fatal",
                        "proposals/clean_geometry_proposal.json",
                        f"Clean proposal binding candidate field {key} is stale.",
                    )
                )

    validation_readiness = binding_validation.get("readiness", {})
    if isinstance(validation_readiness, dict) and audit.get(
        "bindingValidationStatus"
    ) != validation_readiness.get("status"):
        issues.append(
            _issue(
                "clean_geometry_proposal_binding_validation_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal binding validation status is stale.",
            )
        )
    validation_aggregate = binding_validation.get("aggregate", {})
    validation_quality = binding_validation.get("quality", {})
    if isinstance(validation_aggregate, dict) and isinstance(validation_quality, dict):
        expected_validation_fields = {
            "bindingValidationMaxOffsetMeters": validation_aggregate.get(
                "maxCleanupToSettledOffsetMeters"
            ),
            "bindingValidationRmsOffsetMeters": validation_aggregate.get(
                "rmsCleanupToSettledOffsetMeters"
            ),
            "bindingValidationFailedCheckCount": validation_quality.get("failedCheckCount"),
            "bindingValidationNotRunCheckCount": validation_quality.get("notRunCheckCount"),
        }
        for key, expected in expected_validation_fields.items():
            if audit.get(key) != expected:
                issues.append(
                    _issue(
                        "clean_geometry_proposal_binding_validation_mismatch",
                        "fatal",
                        "proposals/clean_geometry_proposal.json",
                        f"Clean proposal binding validation field {key} is stale.",
                    )
                )

    repair_plan_readiness = repair_plan.get("readiness", {})
    if isinstance(repair_plan_readiness, dict) and audit.get(
        "repairRetopologyPlanStatus"
    ) != repair_plan_readiness.get("status"):
        issues.append(
            _issue(
                "clean_geometry_proposal_repair_retopology_plan_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal repair/retopology plan status is stale.",
            )
        )
    repair_plan_aggregate = repair_plan.get("aggregate", {})
    if isinstance(repair_plan_aggregate, dict):
        expected_repair_plan_fields = {
            "repairRetopologyRequiredOperationCount": repair_plan_aggregate.get(
                "requiredOperationCount"
            ),
            "repairRetopologyEstimatedComplexity": repair_plan_aggregate.get(
                "estimatedRepairComplexity"
            ),
        }
        for key, expected in expected_repair_plan_fields.items():
            if audit.get(key) != expected:
                issues.append(
                    _issue(
                        "clean_geometry_proposal_repair_retopology_plan_mismatch",
                        "fatal",
                        "proposals/clean_geometry_proposal.json",
                        f"Clean proposal repair/retopology plan field {key} is stale.",
                    )
                )

    repair_result_readiness = repair_result.get("readiness", {})
    if isinstance(repair_result_readiness, dict) and audit.get(
        "repairResultStatus"
    ) != repair_result_readiness.get("status"):
        issues.append(
            _issue(
                "clean_geometry_proposal_repair_result_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal repair result status is stale.",
            )
        )
    repair_result_aggregate = repair_result.get("aggregate", {})
    if isinstance(repair_result_aggregate, dict):
        expected_repair_result_fields = {
            "repairResultMovedVertexCount": repair_result_aggregate.get("movedVertexCount"),
            "repairResultDeferredOperationCount": repair_result_aggregate.get(
                "deferredOperationCount"
            ),
            "repairResultMaxOutputToSettledOffsetMeters": repair_result_aggregate.get(
                "maxOutputToSettledOffsetMeters"
            ),
        }
        for key, expected in expected_repair_result_fields.items():
            if audit.get(key) != expected:
                issues.append(
                    _issue(
                        "clean_geometry_proposal_repair_result_mismatch",
                        "fatal",
                        "proposals/clean_geometry_proposal.json",
                        f"Clean proposal repair result field {key} is stale.",
                    )
                )

    runtime_binding_readiness = runtime_binding_result.get("readiness", {})
    if isinstance(runtime_binding_readiness, dict) and audit.get(
        "runtimeBindingResultStatus"
    ) != runtime_binding_readiness.get("status"):
        issues.append(
            _issue(
                "clean_geometry_proposal_runtime_binding_result_mismatch",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal runtime binding result status is stale.",
            )
        )
    runtime_binding_aggregate = runtime_binding_result.get("aggregate", {})
    runtime_binding_quality = runtime_binding_result.get("quality", {})
    if isinstance(runtime_binding_aggregate, dict) and isinstance(runtime_binding_quality, dict):
        expected_runtime_binding_fields = {
            "runtimeBindingResultQualityStatus": runtime_binding_quality.get("status"),
            "runtimeBindingRecordCount": runtime_binding_aggregate.get("runtimeBindingRecordCount"),
            "runtimeBindingAccepted": runtime_binding_aggregate.get("runtimeBindingAccepted"),
            "runtimeBindingMaxReconstructionError": runtime_binding_aggregate.get(
                "maxReconstructionError"
            ),
            "runtimeBindingFailedOrWarnCheckCount": runtime_binding_aggregate.get(
                "failedOrWarnCheckCount"
            ),
            "simulationBindingRecordCount": runtime_binding_aggregate.get(
                "runtimeBindingRecordCount"
            ),
        }
        for key, expected in expected_runtime_binding_fields.items():
            if audit.get(key) != expected:
                issues.append(
                    _issue(
                        "clean_geometry_proposal_runtime_binding_result_mismatch",
                        "fatal",
                        "proposals/clean_geometry_proposal.json",
                        f"Clean proposal runtime binding result field {key} is stale.",
                    )
                )

    material_transfer_readiness = material_uv_transfer.get("readiness", {})
    material_transfer_aggregate = material_uv_transfer.get("aggregate", {})
    if isinstance(material_transfer_readiness, dict) and isinstance(
        material_transfer_aggregate, dict
    ):
        expected_material_fields = {
            "materialUvTransferStatus": material_transfer_readiness.get("status"),
            "materialUvTransferRun": material_transfer_aggregate.get("uvTransferAccepted")
            and material_transfer_aggregate.get("materialTransferAccepted"),
            "materialTransferAccepted": material_transfer_readiness.get(
                "acceptedForMaterialPreview"
            ),
            "materialTransferTransferredMaterialCount": material_transfer_aggregate.get(
                "transferredMaterialCount"
            ),
            "materialTransferMissingMaterialCount": material_transfer_aggregate.get(
                "missingMaterialCount"
            ),
            "materialTransferMissingUvCount": material_transfer_aggregate.get("missingUvCount"),
        }
        for key, expected in expected_material_fields.items():
            if audit.get(key) != expected:
                issues.append(
                    _issue(
                        "clean_geometry_proposal_material_uv_transfer_mismatch",
                        "fatal",
                        "proposals/clean_geometry_proposal.json",
                        f"Clean proposal material/UV transfer field {key} is stale.",
                    )
                )

    visual_shell_readiness = visual_shell_review.get("readiness", {})
    visual_shell_quality = visual_shell_review.get("quality", {})
    visual_shell_aggregate = visual_shell_review.get("aggregate", {})
    if (
        isinstance(visual_shell_readiness, dict)
        and isinstance(visual_shell_quality, dict)
        and isinstance(visual_shell_aggregate, dict)
    ):
        expected_visual_fields = {
            "visualShellReviewStatus": visual_shell_readiness.get("status"),
            "visualShellReviewQualityStatus": visual_shell_quality.get("status"),
            "visualFidelityReviewRun": visual_shell_aggregate.get("visualFidelityReviewRun"),
            "visualFidelityScore": visual_shell_aggregate.get("visualFidelityScore"),
            "providerVisualFidelityAccepted": visual_shell_readiness.get(
                "acceptedForVisualFidelity"
            ),
            "renderedPixelComparisonRun": visual_shell_aggregate.get("renderedPixelComparisonRun"),
            "singleShellWeldProofRun": visual_shell_aggregate.get("singleShellWeldProofRun"),
            "singleShellWeldProven": visual_shell_readiness.get("singleShellWeldProven"),
        }
        for key, expected in expected_visual_fields.items():
            if audit.get(key) != expected:
                issues.append(
                    _issue(
                        "clean_geometry_proposal_visual_shell_review_mismatch",
                        "fatal",
                        "proposals/clean_geometry_proposal.json",
                        f"Clean proposal visual/shell review field {key} is stale.",
                    )
                )

    clean_gate_readiness = clean_acceptance_gate.get("readiness", {})
    clean_gate_quality = clean_acceptance_gate.get("quality", {})
    clean_gate_aggregate = clean_acceptance_gate.get("aggregate", {})
    if (
        isinstance(clean_gate_readiness, dict)
        and isinstance(clean_gate_quality, dict)
        and isinstance(clean_gate_aggregate, dict)
    ):
        expected_gate_fields = {
            "cleanAcceptanceGateStatus": clean_gate_readiness.get("status"),
            "cleanAcceptanceGateQualityStatus": clean_gate_quality.get("status"),
            "cleanAcceptanceGateFailedCheckCount": clean_gate_aggregate.get("failedCheckCount"),
            "cleanAcceptanceGateWarningCheckCount": clean_gate_aggregate.get("warningCheckCount"),
            "cleanAcceptanceGateNotRunCheckCount": clean_gate_aggregate.get("notRunCheckCount"),
        }
        for key, expected in expected_gate_fields.items():
            if audit.get(key) != expected:
                issues.append(
                    _issue(
                        "clean_geometry_proposal_clean_acceptance_gate_mismatch",
                        "fatal",
                        "proposals/clean_geometry_proposal.json",
                        f"Clean proposal clean acceptance gate field {key} is stale.",
                    )
                )

    rejection_reasons = quality.get("rejectionReasons", [])
    if not isinstance(rejection_reasons, list):
        rejection_reasons = []
    required_rejections = _required_clean_rejections_for_state(cleanup)
    for reason in required_rejections:
        if reason not in rejection_reasons:
            issues.append(
                _issue(
                    "clean_geometry_proposal_rejection_reason_missing",
                    "fatal",
                    "proposals/clean_geometry_proposal.json",
                    "Clean proposal must retain required rejection reasons.",
                    reason,
                )
            )

    if (
        policy.get("allowExternalApis") is not False
        or policy.get("allowTrainingUse") is not False
        or policy.get("containsUserImagery") is not False
        or policy.get("containsPersonalBodyData") is not False
        or policy.get("approvedDomain") != "avatar_and_garment_only"
    ):
        issues.append(
            _issue(
                "clean_geometry_proposal_policy_violation",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                (
                    "Clean proposal rejection report cannot permit external APIs, "
                    "training use or user data."
                ),
            )
        )

    if clean_quality is not None:
        expected_quality = {
            "proposalId": clean_proposal.get("proposalId"),
            "sourceRawProposalId": clean_proposal.get("sourceRawProposalId"),
            "sourceProviderRegistryId": clean_proposal.get("sourceProviderRegistryId"),
            "cleanProposalAvailable": clean.get("available"),
            "acceptedForCanonical": quality.get("acceptedForCanonical"),
            "cleanupRun": cleanup.get("cleanupRun"),
            "repairRun": cleanup.get("repairRun"),
            "semanticTransferRun": cleanup.get("semanticTransferRun"),
            "simulationBindingRun": cleanup.get("simulationBindingRun"),
            "topologyDiagnosticsRun": cleanup.get("topologyDiagnosticsRun"),
            "cleanupPlanGenerated": cleanup.get("cleanupPlanGenerated"),
            "cleanupResultGenerated": cleanup.get("cleanupResultGenerated"),
            "semanticTransferReportGenerated": cleanup.get("semanticTransferReportGenerated"),
            "bindingCandidateReportGenerated": cleanup.get("bindingCandidateReportGenerated"),
            "bindingValidationReportGenerated": cleanup.get("bindingValidationReportGenerated"),
            "repairRetopologyPlanGenerated": cleanup.get("repairRetopologyPlanGenerated"),
            "partialRepairResultGenerated": cleanup.get("partialRepairResultGenerated"),
            "runtimeBindingResultGenerated": cleanup.get("runtimeBindingResultGenerated"),
            "materialUvTransferReportGenerated": cleanup.get("materialUvTransferReportGenerated"),
            "visualShellReviewGenerated": cleanup.get("visualShellReviewGenerated"),
            "retopologyRun": cleanup.get("retopologyRun"),
            "seamSplitRun": cleanup.get("seamSplitRun"),
            "componentStitchingRun": cleanup.get("componentStitchingRun"),
            "normalContinuityValidationRun": cleanup.get("normalContinuityValidationRun"),
            "tangentContinuityValidationRun": cleanup.get("tangentContinuityValidationRun"),
            "deformationReprojectionRun": cleanup.get("deformationReprojectionRun"),
            "runtimeBindingWritten": cleanup.get("runtimeBindingWritten"),
            "runtimeBindingAccepted": cleanup.get("runtimeBindingAccepted"),
            "cleanAcceptanceGateGenerated": cleanup.get("cleanAcceptanceGateGenerated"),
            "cleanAcceptanceGateRun": cleanup.get("cleanAcceptanceGateRun"),
            "cleanAcceptanceGateAccepted": cleanup.get("cleanAcceptanceGateAccepted"),
            "visualFidelityReviewRun": cleanup.get("visualFidelityReviewRun"),
            "providerVisualFidelityAccepted": cleanup.get("providerVisualFidelityAccepted"),
            "singleShellWeldProofRun": cleanup.get("singleShellWeldProofRun"),
            "singleShellWeldProven": cleanup.get("singleShellWeldProven"),
            "uvTransferRun": cleanup.get("uvTransferRun"),
            "materialTransferRun": cleanup.get("materialTransferRun"),
            "materialTransferAccepted": cleanup.get("materialTransferAccepted"),
            "connectedComponentAnalysisRun": cleanup.get("connectedComponentAnalysisRun"),
            "nonManifoldAnalysisRun": cleanup.get("nonManifoldAnalysisRun"),
            "cleanupPlanStatus": audit.get("cleanupPlanStatus"),
            "cleanupResultStatus": audit.get("cleanupResultStatus"),
            "cleanupPreviewAssetPath": audit.get("cleanupPreviewAssetPath"),
            "postCleanupDuplicatePositionCount": audit.get("postCleanupDuplicatePositionCount"),
            "semanticTransferStatus": audit.get("semanticTransferStatus"),
            "transferredPanelCount": audit.get("transferredPanelCount"),
            "classifiedBoundaryEdgeCount": audit.get("classifiedBoundaryEdgeCount"),
            "unclassifiedBoundaryEdgeCount": audit.get("unclassifiedBoundaryEdgeCount"),
            "bindingCandidateStatus": audit.get("bindingCandidateStatus"),
            "bindingCandidateMappedVertexCount": audit.get("bindingCandidateMappedVertexCount"),
            "bindingCandidateUnmappedVertexCount": audit.get("bindingCandidateUnmappedVertexCount"),
            "bindingCandidateCompleteness": audit.get("bindingCandidateCompleteness"),
            "bindingValidationStatus": audit.get("bindingValidationStatus"),
            "bindingValidationMaxOffsetMeters": audit.get("bindingValidationMaxOffsetMeters"),
            "bindingValidationRmsOffsetMeters": audit.get("bindingValidationRmsOffsetMeters"),
            "bindingValidationFailedCheckCount": audit.get("bindingValidationFailedCheckCount"),
            "bindingValidationNotRunCheckCount": audit.get("bindingValidationNotRunCheckCount"),
            "repairRetopologyPlanStatus": audit.get("repairRetopologyPlanStatus"),
            "repairRetopologyRequiredOperationCount": audit.get(
                "repairRetopologyRequiredOperationCount"
            ),
            "repairRetopologyEstimatedComplexity": audit.get("repairRetopologyEstimatedComplexity"),
            "repairResultStatus": audit.get("repairResultStatus"),
            "repairResultMovedVertexCount": audit.get("repairResultMovedVertexCount"),
            "repairResultDeferredOperationCount": audit.get("repairResultDeferredOperationCount"),
            "repairResultMaxOutputToSettledOffsetMeters": audit.get(
                "repairResultMaxOutputToSettledOffsetMeters"
            ),
            "runtimeBindingResultStatus": audit.get("runtimeBindingResultStatus"),
            "runtimeBindingResultQualityStatus": audit.get("runtimeBindingResultQualityStatus"),
            "runtimeBindingRecordCount": audit.get("runtimeBindingRecordCount"),
            "runtimeBindingMaxReconstructionError": audit.get(
                "runtimeBindingMaxReconstructionError"
            ),
            "runtimeBindingFailedOrWarnCheckCount": audit.get(
                "runtimeBindingFailedOrWarnCheckCount"
            ),
            "materialUvTransferStatus": audit.get("materialUvTransferStatus"),
            "materialUvTransferRun": audit.get("materialUvTransferRun"),
            "materialTransferTransferredMaterialCount": audit.get(
                "materialTransferTransferredMaterialCount"
            ),
            "materialTransferMissingMaterialCount": audit.get(
                "materialTransferMissingMaterialCount"
            ),
            "materialTransferMissingUvCount": audit.get("materialTransferMissingUvCount"),
            "visualShellReviewStatus": audit.get("visualShellReviewStatus"),
            "visualShellReviewQualityStatus": audit.get("visualShellReviewQualityStatus"),
            "visualFidelityScore": audit.get("visualFidelityScore"),
            "renderedPixelComparisonRun": audit.get("renderedPixelComparisonRun"),
            "cleanAcceptanceGateStatus": audit.get("cleanAcceptanceGateStatus"),
            "cleanAcceptanceGateQualityStatus": audit.get("cleanAcceptanceGateQualityStatus"),
            "cleanAcceptanceGateFailedCheckCount": audit.get("cleanAcceptanceGateFailedCheckCount"),
            "cleanAcceptanceGateWarningCheckCount": audit.get(
                "cleanAcceptanceGateWarningCheckCount"
            ),
            "cleanAcceptanceGateNotRunCheckCount": audit.get("cleanAcceptanceGateNotRunCheckCount"),
            "failureReason": audit.get("failureReason"),
        }
        for key, expected in expected_quality.items():
            if clean_quality.get(key) != expected:
                issues.append(
                    _issue(
                        "clean_geometry_proposal_quality_mismatch",
                        "fatal",
                        "reports/clean_geometry_proposal_quality.json",
                        f"Clean proposal quality field {key} must match the proposal.",
                    )
                )

    caps = manifest.get("capabilities", {})
    if isinstance(caps, dict) and caps.get("cleanGeometryProposalAvailable") is not False:
        issues.append(
            _issue(
                "clean_geometry_proposal_capability_invalid",
                "fatal",
                "manifest.json",
                "Clean geometry proposal availability must remain false until cleanup succeeds.",
            )
        )
    if _contains_nonfinite(clean_proposal):
        issues.append(
            _issue(
                "clean_geometry_proposal_nonfinite_numeric_value",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean geometry proposal report must not contain NaN or Infinity.",
            )
        )


def _validate_pattern(package_dir: Path, issues: list[ValidationIssue]) -> None:
    pattern = _read_required_json(package_dir, "pattern/pattern.json", issues)
    if pattern is None:
        return
    panel_ids = [panel["id"] for panel in pattern.get("panels", [])]
    if len(panel_ids) != len(set(panel_ids)):
        issues.append(
            _issue(
                "duplicate_panel_id", "fatal", "pattern/pattern.json", "Panel IDs must be unique."
            )
        )
    for required_panel_id in REQUIRED_PANELS:
        if required_panel_id not in panel_ids:
            issues.append(
                _issue(
                    "required_panel_missing",
                    "fatal",
                    "pattern/pattern.json",
                    "Required panel missing.",
                    required_panel_id,
                )
            )
    seam_ids = [seam["id"] for seam in pattern.get("seams", [])]
    if len(seam_ids) != len(set(seam_ids)):
        issues.append(
            _issue("duplicate_seam_id", "fatal", "pattern/pattern.json", "Seam IDs must be unique.")
        )
    edge_ids = {
        edge["id"] for panel in pattern.get("panels", []) for edge in panel.get("boundary", [])
    }
    edge_lengths = _pattern_edge_lengths(pattern, issues)
    for seam in pattern.get("seams", []):
        for span in seam.get("spans", []):
            if span.get("panelId") not in panel_ids or span.get("edgeId") not in edge_ids:
                issues.append(
                    _issue(
                        "dangling_seam_reference",
                        "fatal",
                        "pattern/pattern.json",
                        "Seam references unknown panel or edge.",
                        seam.get("id"),
                    )
                )
            if span.get("orientation") not in {"forward", "reverse"}:
                issues.append(
                    _issue(
                        "invalid_seam_orientation",
                        "fatal",
                        "pattern/pattern.json",
                        "Seam span orientation must be forward or reverse.",
                        seam.get("id"),
                    )
                )
        _validate_seam_ease(seam, edge_lengths, issues)
    for seam in REQUIRED_SEAMS:
        if seam not in seam_ids:
            issues.append(
                _issue(
                    "required_seam_missing",
                    "fatal",
                    "pattern/pattern.json",
                    "Required seam missing.",
                    seam,
                )
            )
    openings = {opening.get("id") for opening in pattern.get("openings", [])}
    for opening in REQUIRED_OPENINGS:
        if opening not in openings:
            issues.append(
                _issue(
                    "required_opening_missing",
                    "fatal",
                    "pattern/pattern.json",
                    "Required opening missing.",
                    opening,
                )
            )
    for opening_doc in pattern.get("openings", []):
        if opening_doc.get("id") in REQUIRED_OPENINGS and opening_doc.get("status") != "open":
            issues.append(
                _issue(
                    "required_opening_filled",
                    "fatal",
                    "pattern/pattern.json",
                    "Implementation 01 neck, cuff and hem openings must remain open.",
                    opening_doc.get("id"),
                )
            )
    for panel_doc in pattern.get("panels", []):
        try:
            boundary_issues = validate_panel_boundary(panel_doc)
        except Exception as exc:
            issues.append(
                _issue(
                    "invalid_curve", "fatal", "pattern/pattern.json", str(exc), panel_doc.get("id")
                )
            )
            continue
        for boundary_issue in boundary_issues:
            issues.append(
                _issue(
                    boundary_issue,
                    "fatal",
                    "pattern/pattern.json",
                    "Panel boundary is invalid.",
                    panel_doc.get("id"),
                )
            )
    if _contains_nonfinite(pattern):
        issues.append(
            _issue(
                "nonfinite_numeric_value",
                "fatal",
                "pattern/pattern.json",
                "NaN or Infinity is not allowed.",
            )
        )


def _validate_semantic(package_dir: Path, issues: list[ValidationIssue]) -> None:
    semantic = _read_required_json(package_dir, "semantic/garment_graph.json", issues)
    pattern = _read_required_json(package_dir, "pattern/pattern.json", issues)
    if semantic is None or pattern is None:
        return
    pattern_panel_ids = {panel.get("id") for panel in pattern.get("panels", [])}
    pattern_seam_ids = {seam.get("id") for seam in pattern.get("seams", [])}
    pattern_opening_ids = {opening.get("id") for opening in pattern.get("openings", [])}
    component_ids = [component.get("id") for component in semantic.get("components", [])]
    if len(component_ids) != len(set(component_ids)):
        issues.append(
            _issue(
                "duplicate_component_id",
                "fatal",
                "semantic/garment_graph.json",
                "Component IDs must be unique.",
            )
        )
    for component in semantic.get("components", []):
        for panel_id in component.get("panels", []):
            if panel_id not in pattern_panel_ids:
                issues.append(
                    _issue(
                        "dangling_component_panel_reference",
                        "fatal",
                        "semantic/garment_graph.json",
                        "Component references a panel not present in pattern.json.",
                        component.get("id"),
                    )
                )
    for seam in semantic.get("seams", []):
        if seam.get("id") not in pattern_seam_ids:
            issues.append(
                _issue(
                    "dangling_semantic_seam_reference",
                    "fatal",
                    "semantic/garment_graph.json",
                    "Semantic seam is not present in pattern.json.",
                    seam.get("id"),
                )
            )
    for opening in semantic.get("openings", []):
        if opening.get("id") not in pattern_opening_ids:
            issues.append(
                _issue(
                    "dangling_semantic_opening_reference",
                    "fatal",
                    "semantic/garment_graph.json",
                    "Semantic opening is not present in pattern.json.",
                    opening.get("id"),
                )
            )


def _validate_meshes_and_constraints(package_dir: Path, issues: list[ValidationIssue]) -> None:
    sim_manifest = _read_required_json(package_dir, "simulation/mesh_manifest.json", issues)
    render_manifest = _read_required_json(package_dir, "render/mesh_manifest.json", issues)
    constraints = _read_required_json(package_dir, "simulation/constraints.json", issues)
    if sim_manifest is None or render_manifest is None or constraints is None:
        return
    try:
        sim_mesh = _meshset_from_manifest(sim_manifest)
        render_mesh = _meshset_from_manifest(render_manifest)
    except ValueError as exc:
        issues.append(
            _issue("mesh_manifest_invalid", "fatal", "simulation/mesh_manifest.json", str(exc))
        )
        return
    for rel, manifest, meshset in [
        ("simulation/mesh_manifest.json", sim_manifest, sim_mesh),
        ("render/mesh_manifest.json", render_manifest, render_mesh),
    ]:
        if not finite_mesh(meshset):
            issues.append(
                _issue(
                    "mesh_nonfinite_or_invalid",
                    "fatal",
                    rel,
                    "Mesh contains nonfinite data or invalid triangles.",
                )
            )
        _validate_triangle_quality(rel, meshset, issues)
        if manifest.get("topologyHash") != topology_hash(meshset):
            issues.append(
                _issue(
                    "mesh_topology_hash_mismatch",
                    "fatal",
                    rel,
                    "Mesh topology hash does not match manifest.",
                )
            )
        if manifest.get("contentHash") != geometry_content_hash(meshset):
            issues.append(
                _issue(
                    "mesh_content_hash_mismatch",
                    "fatal",
                    rel,
                    "Mesh content hash does not match manifest.",
                )
            )
    for constraint in constraints.get("constraints", []):
        for span_key in ["spanA", "spanB"]:
            span = constraint.get(span_key, {})
            mesh_index = int(span.get("meshIndex", -1))
            vertex_index = int(span.get("vertexIndex", -1))
            if mesh_index < 0 or mesh_index >= len(sim_mesh.meshes):
                issues.append(
                    _issue(
                        "invalid_constraint_mesh_index",
                        "fatal",
                        "simulation/constraints.json",
                        "Constraint mesh index is invalid.",
                        constraint.get("id"),
                    )
                )
                continue
            if vertex_index < 0 or vertex_index >= len(sim_mesh.meshes[mesh_index].vertices):
                issues.append(
                    _issue(
                        "invalid_constraint_vertex",
                        "fatal",
                        "simulation/constraints.json",
                        "Constraint vertex index is invalid.",
                        constraint.get("id"),
                    )
                )


def _validate_settle_state(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    caps = manifest.get("capabilities", {})
    material = _read_required_json(package_dir, "simulation/material_physics.json", issues)
    sim_manifest = _read_required_json(package_dir, "simulation/mesh_manifest.json", issues)
    rest_state = _read_required_json(package_dir, "simulation/rest_state.json", issues)
    settled_state = _read_required_json(package_dir, "simulation/settled_state.json", issues)
    diagnostics = _read_required_json(package_dir, "simulation/settle_diagnostics.json", issues)
    if (
        material is None
        or sim_manifest is None
        or rest_state is None
        or settled_state is None
        or diagnostics is None
    ):
        return
    cloth_available = bool(caps.get("actualClothSettleAvailable"))
    if cloth_available and not material.get("clothSettleRun"):
        issues.append(
            _issue(
                "cloth_settle_material_contradiction",
                "fatal",
                "simulation/material_physics.json",
                "Manifest claims settle availability but material preset says no settle ran.",
            )
        )
    if cloth_available and diagnostics.get("convergenceState") != "converged":
        issues.append(
            _issue(
                "cloth_settle_not_converged",
                "fatal",
                "simulation/settle_diagnostics.json",
                "Settled state must report convergence before capability is enabled.",
            )
        )
    if float(diagnostics.get("maximumBodyPenetrationMeters", 1.0)) > 0.012:
        issues.append(
            _issue(
                "cloth_settle_body_penetration_too_high",
                "fatal",
                "simulation/settle_diagnostics.json",
                "Maximum body penetration exceeds reference threshold.",
            )
        )
    if float(diagnostics.get("rmsSeamResidualMeters", 1.0)) > 0.035:
        issues.append(
            _issue(
                "cloth_settle_seam_residual_too_high",
                "fatal",
                "simulation/settle_diagnostics.json",
                "RMS seam residual exceeds reference threshold.",
            )
        )
    if int(diagnostics.get("nonFiniteValueCount", 1)) != 0:
        issues.append(
            _issue(
                "cloth_settle_nonfinite",
                "fatal",
                "simulation/settle_diagnostics.json",
                "Settled simulation state contains non-finite values.",
            )
        )
    if int(diagnostics.get("invertedOrDegenerateElementCount", 1)) != 0:
        issues.append(
            _issue(
                "cloth_settle_degenerate_elements",
                "fatal",
                "simulation/settle_diagnostics.json",
                "Settled simulation state contains inverted or degenerate elements.",
            )
        )
    if diagnostics.get("settledTopologyHash") != sim_manifest.get("topologyHash"):
        issues.append(
            _issue(
                "settled_topology_hash_mismatch",
                "fatal",
                "simulation/settle_diagnostics.json",
                "Settled topology hash must match simulation mesh topology.",
            )
        )
    if diagnostics.get("settledContentHash") != sim_manifest.get("contentHash"):
        issues.append(
            _issue(
                "settled_content_hash_mismatch",
                "fatal",
                "simulation/settle_diagnostics.json",
                "Settled content hash must match simulation mesh content.",
            )
        )
    if settled_state.get("meshTopologyHash") != sim_manifest.get("topologyHash"):
        issues.append(
            _issue(
                "settled_state_topology_hash_mismatch",
                "fatal",
                "simulation/settled_state.json",
                "Settled state topology hash must match simulation mesh topology.",
            )
        )
    if settled_state.get("meshContentHash") != sim_manifest.get("contentHash"):
        issues.append(
            _issue(
                "settled_state_content_hash_mismatch",
                "fatal",
                "simulation/settled_state.json",
                "Settled state content hash must match simulation mesh content.",
            )
        )
    if rest_state.get("meshTopologyHash") != sim_manifest.get("topologyHash"):
        issues.append(
            _issue(
                "rest_state_topology_hash_mismatch",
                "fatal",
                "simulation/rest_state.json",
                "Rest and settled simulation states must share topology.",
            )
        )
    if (
        _contains_nonfinite(rest_state)
        or _contains_nonfinite(settled_state)
        or _contains_nonfinite(diagnostics)
    ):
        issues.append(
            _issue(
                "settle_state_nonfinite_numeric_value",
                "fatal",
                "simulation/settled_state.json",
                "Simulation state and diagnostics must not contain NaN or Infinity.",
            )
        )


def _validate_self_collision_report(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    report = _read_required_json(package_dir, "reports/self_collision_report.json", issues)
    rest_state = _read_required_json(package_dir, "simulation/rest_state.json", issues)
    settled_state = _read_required_json(package_dir, "simulation/settled_state.json", issues)
    sim_manifest = _read_required_json(package_dir, "simulation/mesh_manifest.json", issues)
    constraints = _read_required_json(package_dir, "simulation/constraints.json", issues)
    diagnostics = _read_required_json(package_dir, "simulation/settle_diagnostics.json", issues)
    if (
        report is None
        or rest_state is None
        or settled_state is None
        or sim_manifest is None
        or constraints is None
    ):
        return
    if report.get("garmentId") != manifest.get("garmentId"):
        issues.append(
            _issue(
                "self_collision_report_garment_mismatch",
                "fatal",
                "reports/self_collision_report.json",
                "Self-collision report must reference the package garment ID.",
            )
        )
    if report.get("garmentClass") != manifest.get("garmentClass"):
        issues.append(
            _issue(
                "self_collision_report_class_mismatch",
                "fatal",
                "reports/self_collision_report.json",
                "Self-collision report must reference the package garment class.",
            )
        )
    if _nested_string(report, ["integrity", "selfCollisionReportHash"], "") != (
        hash_self_collision_report(report)
    ):
        issues.append(
            _issue(
                "self_collision_report_hash_mismatch",
                "fatal",
                "reports/self_collision_report.json",
                "Self-collision report hash must match its canonical payload.",
            )
        )
    try:
        rest_mesh = _meshset_from_state_and_manifest(rest_state, sim_manifest)
        settled_mesh = _meshset_from_state_and_manifest(settled_state, sim_manifest)
        expected = build_self_collision_report(
            garment_id=str(manifest["garmentId"]),
            garment_class=str(manifest["garmentClass"]),
            rest_mesh=rest_mesh,
            settled_mesh=settled_mesh,
            seam_constraints=constraints,
        )
    except Exception as exc:
        issues.append(
            _issue(
                "self_collision_report_recompute_failed",
                "fatal",
                "reports/self_collision_report.json",
                str(exc),
            )
        )
        return
    for key in [
        "sourceAssets",
        "settings",
        "execution",
        "metrics",
        "adversarialFixtures",
        "timingProfile",
        "readiness",
        "policy",
    ]:
        if report.get(key) != expected.get(key):
            issues.append(
                _issue(
                    "self_collision_report_recompute_mismatch",
                    "fatal",
                    "reports/self_collision_report.json",
                    "Self-collision evidence must recompute from persisted simulation states.",
                    key,
                )
            )
    readiness = report.get("readiness", {})
    metrics = report.get("metrics", {})
    if (
        not isinstance(readiness, dict)
        or readiness.get("acceptedForProductionGpuSolver") is not False
        or "unsupported_high_velocity_tunnelling" not in readiness.get("limitations", [])
    ):
        issues.append(
            _issue(
                "self_collision_readiness_invalid",
                "fatal",
                "reports/self_collision_report.json",
                "Self-collision may claim only D0 reference availability in this increment.",
            )
        )
    if not isinstance(metrics, dict):
        issues.append(
            _issue(
                "self_collision_metrics_invalid",
                "fatal",
                "reports/self_collision_report.json",
                "Self-collision report metrics must be an object.",
            )
        )
    elif int(metrics.get("unresolvedContactCount", 1)) != 0:
        issues.append(
            _issue(
                "self_collision_unresolved_contacts",
                "warning",
                "reports/self_collision_report.json",
                "D0 reference self-collision ran but retained unresolved contacts.",
            )
        )
    if diagnostics is not None:
        self_collision = diagnostics.get("selfCollision", {})
        if (
            not isinstance(self_collision, dict)
            or self_collision.get("available") is not True
            or self_collision.get("reportRef") != "reports/self_collision_report.json"
        ):
            issues.append(
                _issue(
                    "self_collision_diagnostics_contradiction",
                    "fatal",
                    "simulation/settle_diagnostics.json",
                    "Settle diagnostics must point to the executed self-collision report.",
                )
            )
    caps = manifest.get("capabilities", {})
    if isinstance(caps, dict):
        if caps.get("selfCollisionAvailable") is not True:
            issues.append(
                _issue(
                    "self_collision_capability_missing",
                    "fatal",
                    "manifest.json",
                    "Manifest must declare executed self-collision availability.",
                )
            )
        if caps.get("selfCollisionEvidenceAvailable") is not True:
            issues.append(
                _issue(
                    "self_collision_evidence_capability_missing",
                    "fatal",
                    "manifest.json",
                    "Manifest must declare self-collision evidence availability.",
                )
            )
    warnings = manifest.get("warnings", [])
    if isinstance(warnings, list) and "self_collision_not_run" in warnings:
        issues.append(
            _issue(
                "self_collision_warning_contradiction",
                "fatal",
                "manifest.json",
                "Executed self-collision evidence contradicts self_collision_not_run.",
            )
        )
    if _contains_nonfinite(report):
        issues.append(
            _issue(
                "self_collision_report_nonfinite_numeric_value",
                "fatal",
                "reports/self_collision_report.json",
                "Self-collision report must not contain NaN or Infinity.",
            )
        )


def _validate_glbs(package_dir: Path, issues: list[ValidationIssue]) -> None:
    for rel in [
        "avatar/reference_avatar.glb",
        "avatar/collision.glb",
        "proposals/manual_raw_visual_proposal.glb",
        "proposals/manual_cleanup_preview.glb",
        "proposals/manual_repair_preview.glb",
        "proposals/manual_runtime_retopology_preview.glb",
        "simulation/simulation_mesh.glb",
        "render/fallback.glb",
        "render/stitched_shell.glb",
    ]:
        try:
            audit = audit_glb(package_dir / rel)
            if audit["primitiveCount"] <= 0 or audit["triangleEstimate"] <= 0:
                issues.append(
                    _issue(
                        "glb_has_no_renderable_geometry",
                        "fatal",
                        rel,
                        "GLB must contain renderable triangles.",
                    )
                )
        except Exception as exc:
            issues.append(_issue("glb_parse_failed", "fatal", rel, str(exc)))


def _validate_binding(package_dir: Path, issues: list[ValidationIssue]) -> None:
    try:
        binding = read_binding(package_dir / "binding" / "sim_to_render.bin")
    except Exception as exc:
        issues.append(_issue("binding_invalid", "fatal", "binding/sim_to_render.bin", str(exc)))
        return
    manifest = _read_required_json(package_dir, "binding/binding_manifest.json", issues)
    sim_manifest = _read_required_json(package_dir, "simulation/mesh_manifest.json", issues)
    render_manifest = _read_required_json(package_dir, "render/mesh_manifest.json", issues)
    if manifest is None or sim_manifest is None or render_manifest is None:
        return
    if binding.simulation_topology_hash != manifest.get("simulationTopologyHash"):
        issues.append(
            _issue(
                "binding_sim_topology_hash_mismatch",
                "fatal",
                "binding/binding_manifest.json",
                "Simulation topology hash mismatch.",
            )
        )
    if binding.render_topology_hash != manifest.get("renderTopologyHash"):
        issues.append(
            _issue(
                "binding_render_topology_hash_mismatch",
                "fatal",
                "binding/binding_manifest.json",
                "Render topology hash mismatch.",
            )
        )
    for record in binding.records:
        if record.simulation_triangle_index >= binding.simulation_triangle_count:
            issues.append(
                _issue(
                    "binding_triangle_out_of_range",
                    "fatal",
                    "binding/sim_to_render.bin",
                    "Triangle index out of range.",
                )
            )
        if (
            record.barycentric_u < -1e-6
            or record.barycentric_v < -1e-6
            or record.barycentric_u + record.barycentric_v > 1.000001
        ):
            issues.append(
                _issue(
                    "binding_barycentric_invalid",
                    "fatal",
                    "binding/sim_to_render.bin",
                    "Barycentric coordinates outside tolerance.",
                )
            )
        if record.panel_table_index >= binding.panel_count:
            issues.append(
                _issue(
                    "binding_panel_index_invalid",
                    "fatal",
                    "binding/sim_to_render.bin",
                    "Panel table index out of range.",
                )
            )
    try:
        sim_mesh = _meshset_from_manifest(sim_manifest)
        render_mesh = _meshset_from_manifest(render_manifest)
        reconstructed = reconstruct_vertices(sim_mesh, binding)
        max_error, rms_error = reconstruction_error(render_mesh, reconstructed)
        if max_error > float(manifest.get("reconstructionTolerance", 1e-6)):
            issues.append(
                _issue(
                    "binding_reconstruction_error_too_high",
                    "fatal",
                    "binding/sim_to_render.bin",
                    f"Maximum reconstruction error {max_error:.8f} exceeds tolerance.",
                )
            )
        if abs(max_error - float(manifest.get("maximumReconstructionError", 0.0))) > 1e-6:
            issues.append(
                _issue(
                    "binding_reconstruction_report_mismatch",
                    "fatal",
                    "binding/binding_manifest.json",
                    "Binding maximum error report is stale.",
                )
            )
        if abs(rms_error - float(manifest.get("rmsReconstructionError", 0.0))) > 1e-6:
            issues.append(
                _issue(
                    "binding_reconstruction_report_mismatch",
                    "fatal",
                    "binding/binding_manifest.json",
                    "Binding RMS error report is stale.",
                )
            )
    except Exception as exc:
        issues.append(
            _issue("binding_reconstruction_failed", "fatal", "binding/sim_to_render.bin", str(exc))
        )


def _validate_capabilities(manifest: dict[str, Any], issues: list[ValidationIssue]) -> None:
    caps = manifest.get("capabilities", {})
    if not caps.get("actualClothSettleAvailable"):
        issues.append(
            _issue(
                "cloth_settle_not_run",
                "warning",
                "manifest.json",
                "No physical cloth-settle solver ran in Implementation 01.",
            )
        )
    if caps.get("actualClothSettleAvailable") and "cloth_settle_not_run" in manifest.get(
        "warnings", []
    ):
        issues.append(
            _issue(
                "capability_warning_contradiction",
                "fatal",
                "manifest.json",
                "actualClothSettleAvailable contradicts cloth_settle_not_run warning.",
            )
        )
    if not caps.get("selfCollisionAvailable"):
        issues.append(
            _issue(
                "self_collision_not_run",
                "warning",
                "manifest.json",
                "Reference solver does not implement self-collision.",
            )
        )
    if caps.get("selfCollisionAvailable") and "self_collision_not_run" in manifest.get(
        "warnings", []
    ):
        issues.append(
            _issue(
                "capability_warning_contradiction",
                "fatal",
                "manifest.json",
                "selfCollisionAvailable contradicts self_collision_not_run warning.",
            )
        )
    if (
        caps.get("selfCollisionAvailable")
        and caps.get("selfCollisionEvidenceAvailable") is not True
    ):
        issues.append(
            _issue(
                "self_collision_evidence_capability_missing",
                "fatal",
                "manifest.json",
                "Self-collision availability requires an evidence report capability.",
            )
        )
    if caps.get("productionBindingC3ProfileAvailable") is not True:
        issues.append(
            _issue(
                "production_binding_c3_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest must declare scoped production binding C3 profile evidence.",
            )
        )
    if caps.get("productionBindingContractAvailable") is not True:
        issues.append(
            _issue(
                "production_binding_contract_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest must declare a production binding contract.",
            )
        )
    if caps.get("geometryMaterialUvTransferAvailable") is not True:
        issues.append(
            _issue(
                "geometry_material_uv_transfer_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest must declare material/UV transfer evidence availability.",
            )
        )
    if caps.get("geometryStitchedShellAvailable") is not True:
        issues.append(
            _issue(
                "geometry_stitched_shell_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest must declare stitched-shell output evidence availability.",
            )
        )
    if caps.get("geometryVisualShellReviewAvailable") is not True:
        issues.append(
            _issue(
                "geometry_visual_shell_review_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest must declare visual/shell review evidence availability.",
            )
        )
    if caps.get("renderTangentsPersistedAvailable") is not True:
        issues.append(
            _issue(
                "render_tangents_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest must declare persisted render tangent evidence availability.",
            )
        )
    if caps.get("poseSuiteBindingEvidenceAvailable") is not True:
        issues.append(
            _issue(
                "pose_suite_binding_capability_missing",
                "fatal",
                "manifest.json",
                "Manifest must declare pose-suite binding evidence availability.",
            )
        )
    if caps.get("zeroOneStaticAvailable") or caps.get("zeroOneDynamicAvailable"):
        issues.append(
            _issue(
                "false_zeroone_capability",
                "fatal",
                "manifest.json",
                "ZeroOne derivatives are unavailable and optional.",
            )
        )


def _validate_required_files(package_dir: Path, issues: list[ValidationIssue]) -> None:
    for rel in EXPECTED_FILES:
        try:
            validate_package_relpath(rel)
        except ValueError:
            issues.append(
                _issue("unsafe_expected_path", "fatal", rel, "Internal expected path is invalid.")
            )
            continue
        if not (package_dir / rel).exists():
            issues.append(
                _issue("required_file_missing", "fatal", rel, "Required package file is missing.")
            )
    for path in package_dir.rglob("*"):
        if not path.is_symlink():
            continue
        rel = path.relative_to(package_dir).as_posix()
        try:
            path.resolve().relative_to(package_dir.resolve())
        except ValueError:
            issues.append(_issue("escaping_symlink", "fatal", rel, "Symlink escapes package root."))


def _read_required_json(
    package_dir: Path, rel: str, issues: list[ValidationIssue]
) -> dict[str, Any] | None:
    path = package_dir / rel
    if not path.exists():
        issues.append(
            _issue("required_file_missing", "fatal", rel, "Required JSON file is missing.")
        )
        return None
    try:
        data = read_json(path)
    except Exception as exc:
        issues.append(_issue("json_unreadable", "fatal", rel, str(exc)))
        return None
    if not isinstance(data, dict):
        issues.append(_issue("json_root_not_object", "fatal", rel, "JSON root must be an object."))
        return None
    return data


def _meshset_from_manifest(manifest: dict[str, Any]) -> MeshSet:
    meshes: list[Mesh] = []
    for mesh_doc in manifest.get("meshes", []):
        if "panelUvs" not in mesh_doc:
            raise ValueError("missing_pattern_coordinates")
        meshes.append(
            Mesh(
                name=str(mesh_doc["name"]),
                panel_id=str(mesh_doc["panelId"]),
                vertices=[_vec3(vertex) for vertex in mesh_doc["vertices"]],
                panel_uvs=[_vec2(uv) for uv in mesh_doc["panelUvs"]],
                triangles=[_tri(triangle) for triangle in mesh_doc["triangles"]],
                material_id=str(mesh_doc.get("materialId", "material.cotton_jersey_reference_v1")),
            )
        )
    return MeshSet(meshes)


def _meshset_from_state_and_manifest(state: dict[str, Any], manifest: dict[str, Any]) -> MeshSet:
    state_meshes = state.get("meshes", [])
    manifest_meshes = manifest.get("meshes", [])
    if not isinstance(state_meshes, list) or len(state_meshes) != len(manifest_meshes):
        raise ValueError("state_mesh_count_mismatch")
    meshes: list[Mesh] = []
    for state_mesh, manifest_mesh in zip(state_meshes, manifest_meshes, strict=True):
        positions = state_mesh.get("positions", [])
        if len(positions) != len(manifest_mesh.get("vertices", [])):
            raise ValueError("state_vertex_count_mismatch")
        if str(state_mesh.get("name")) != str(manifest_mesh.get("name")):
            raise ValueError("state_mesh_name_mismatch")
        if str(state_mesh.get("panelId")) != str(manifest_mesh.get("panelId")):
            raise ValueError("state_panel_id_mismatch")
        meshes.append(
            Mesh(
                name=str(manifest_mesh["name"]),
                panel_id=str(manifest_mesh["panelId"]),
                vertices=[_vec3(vertex) for vertex in positions],
                panel_uvs=[_vec2(uv) for uv in manifest_mesh["panelUvs"]],
                triangles=[_tri(triangle) for triangle in manifest_mesh["triangles"]],
                material_id=str(
                    manifest_mesh.get("materialId", "material.cotton_jersey_reference_v1")
                ),
            )
        )
    return MeshSet(meshes)


def _required_clean_rejections_for_state(cleanup: dict[str, Any]) -> list[str]:
    if (
        cleanup.get("cleanupRun") is True
        and cleanup.get("semanticTransferRun") is True
        and cleanup.get("candidateBindingRun") is True
        and cleanup.get("deformationValidationRun") is True
        and cleanup.get("repairRetopologyPlanGenerated") is True
        and cleanup.get("partialRepairResultGenerated") is True
        and cleanup.get("runtimeBindingResultGenerated") is True
        and cleanup.get("runtimeBindingAccepted") is True
        and cleanup.get("cleanAcceptanceGateRun") is True
        and cleanup.get("cleanAcceptanceGateAccepted") is False
    ):
        return CLEAN_ACCEPTANCE_GATE_REJECTION_REASONS
    if (
        cleanup.get("cleanupRun") is True
        and cleanup.get("semanticTransferRun") is True
        and cleanup.get("candidateBindingRun") is True
        and cleanup.get("deformationValidationRun") is True
        and cleanup.get("repairRetopologyPlanGenerated") is True
        and cleanup.get("partialRepairResultGenerated") is True
        and cleanup.get("runtimeBindingResultGenerated") is True
        and cleanup.get("runtimeBindingAccepted") is True
    ):
        return PARTIAL_RUNTIME_BINDING_RESULT_REJECTION_REASONS
    if (
        cleanup.get("cleanupRun") is True
        and cleanup.get("semanticTransferRun") is True
        and cleanup.get("candidateBindingRun") is True
        and cleanup.get("deformationValidationRun") is True
        and cleanup.get("repairRetopologyPlanGenerated") is True
        and cleanup.get("partialRepairResultGenerated") is True
        and cleanup.get("runtimeBindingAccepted") is not True
    ):
        return PARTIAL_REPAIR_RESULT_REJECTION_REASONS
    if (
        cleanup.get("cleanupRun") is True
        and cleanup.get("semanticTransferRun") is True
        and cleanup.get("candidateBindingRun") is True
        and cleanup.get("deformationValidationRun") is True
        and cleanup.get("repairRetopologyPlanGenerated") is True
        and cleanup.get("runtimeBindingAccepted") is not True
    ):
        return PARTIAL_REPAIR_RETOPOLOGY_PLAN_REJECTION_REASONS
    if (
        cleanup.get("cleanupRun") is True
        and cleanup.get("semanticTransferRun") is True
        and cleanup.get("candidateBindingRun") is True
        and cleanup.get("deformationValidationRun") is True
        and cleanup.get("runtimeBindingAccepted") is not True
    ):
        return PARTIAL_BINDING_VALIDATION_REJECTION_REASONS
    if cleanup.get("cleanupRun") is True and cleanup.get("semanticTransferRun") is True:
        return PARTIAL_SEMANTIC_TRANSFER_REJECTION_REASONS
    if cleanup.get("cleanupRun") is True:
        return PARTIAL_CLEANUP_REJECTION_REASONS
    return REQUIRED_CLEAN_REJECTION_REASONS


def _pattern_edge_lengths(
    pattern: dict[str, Any], issues: list[ValidationIssue]
) -> dict[tuple[str, str], float]:
    lengths: dict[tuple[str, str], float] = {}
    for panel in pattern.get("panels", []):
        panel_id = str(panel.get("id", ""))
        for edge in panel.get("boundary", []):
            edge_id = str(edge.get("id", ""))
            try:
                points = sample_curve(edge["curve"], int(edge["sampleCount"]))
            except Exception as exc:
                issues.append(
                    _issue("invalid_curve", "fatal", "pattern/pattern.json", str(exc), edge_id)
                )
                continue
            length = 0.0
            for left, right in zip(points, points[1:], strict=False):
                length += math.dist(left, right)
            lengths[(panel_id, edge_id)] = length
    return lengths


def _validate_seam_ease(
    seam: dict[str, Any],
    edge_lengths: dict[tuple[str, str], float],
    issues: list[ValidationIssue],
) -> None:
    spans = seam.get("spans", [])
    if len(spans) < 2:
        return
    lengths = [
        edge_lengths.get((str(span.get("panelId")), str(span.get("edgeId"))), 0.0) for span in spans
    ]
    nonzero_lengths = [length for length in lengths if length > 1e-6]
    if len(nonzero_lengths) < 2:
        return
    ease_ratio = float(seam.get("easeRatio", 1.0))
    if not 0.70 <= ease_ratio <= 1.25:
        issues.append(
            _issue(
                "seam_ease_incompatible",
                "fatal",
                "pattern/pattern.json",
                "Seam ease ratio is outside the Implementation 01 supported range.",
                seam.get("id"),
            )
        )
        return
    shortest = min(nonzero_lengths)
    longest = max(nonzero_lengths)
    if shortest <= 1e-6 or longest <= 1e-6:
        issues.append(
            _issue(
                "seam_length_incompatible",
                "fatal",
                "pattern/pattern.json",
                "Seam span length is zero or missing.",
                seam.get("id"),
            )
        )


def _validate_triangle_quality(
    rel: str,
    meshset: MeshSet,
    issues: list[ValidationIssue],
) -> None:
    for mesh in meshset.meshes:
        for triangle_index, tri in enumerate(mesh.triangles):
            if any(index < 0 or index >= len(mesh.vertices) for index in tri):
                continue
            a, b, c = mesh.vertices[tri[0]], mesh.vertices[tri[1]], mesh.vertices[tri[2]]
            area2 = math.sqrt(sum(value * value for value in cross(sub(b, a), sub(c, a))))
            if area2 <= 1e-10:
                issues.append(
                    _issue(
                        "degenerate_triangle",
                        "fatal",
                        rel,
                        "Mesh contains a degenerate triangle.",
                        f"{mesh.panel_id}:{triangle_index}",
                    )
                )


def _validate_normalised_mask(mask: dict[str, Any], issues: list[ValidationIssue]) -> None:
    polygons = mask.get("polygons", [])
    if not isinstance(polygons, list) or not polygons:
        issues.append(
            _issue(
                "visual_mask_polygon_missing",
                "fatal",
                "source/visual_observations.json",
                "Mask must include at least one normalised polygon.",
                str(mask.get("maskId", "")),
            )
        )
        return
    for polygon in polygons:
        if not isinstance(polygon, list) or len(polygon) < 3:
            issues.append(
                _issue(
                    "visual_mask_polygon_invalid",
                    "fatal",
                    "source/visual_observations.json",
                    "Mask polygon must contain at least three points.",
                    str(mask.get("maskId", "")),
                )
            )
            continue
        for point in polygon:
            _validate_normalised_point(point, "visual_mask_point_out_of_range", issues)


def _validate_normalised_point(point: Any, code: str, issues: list[ValidationIssue]) -> None:
    if not isinstance(point, list | tuple) or len(point) != 2:
        issues.append(
            _issue(
                code,
                "fatal",
                "source/visual_observations.json",
                "Normalised image point must be [x, y].",
            )
        )
        return
    x = _float_or(point[0], math.nan)
    y = _float_or(point[1], math.nan)
    if not math.isfinite(x) or not math.isfinite(y) or not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
        issues.append(
            _issue(
                code,
                "fatal",
                "source/visual_observations.json",
                "Normalised image point must stay inside [0, 1].",
            )
        )


def _nested_string(data: dict[str, Any], path: list[str], fallback: str) -> str:
    value: Any = data
    for key in path:
        if not isinstance(value, dict):
            return fallback
        value = value.get(key)
    return value if isinstance(value, str) else fallback


def _json_hash(data: dict[str, Any]) -> str:
    return sha256_bytes(canonical_dumps(data).encode("utf-8"))


def _json_hash_with_blank(data: dict[str, Any], hash_key: str) -> str:
    clone = dict(data)
    integrity = clone.get("integrity")
    if isinstance(integrity, dict):
        clone["integrity"] = dict(integrity)
        clone["integrity"][hash_key] = ""
    return _json_hash(clone)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _vec3(value: Any) -> Vec3:
    if not isinstance(value, list | tuple) or len(value) != 3:
        raise ValueError("expected Vec3")
    return (float(value[0]), float(value[1]), float(value[2]))


def _vec2(value: Any) -> Vec2:
    if not isinstance(value, list | tuple) or len(value) != 2:
        raise ValueError("expected Vec2")
    return (float(value[0]), float(value[1]))


def _tri(value: Any) -> Tri:
    if not isinstance(value, list | tuple) or len(value) != 3:
        raise ValueError("expected triangle")
    return (int(value[0]), int(value[1]), int(value[2]))


def _int_or(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _float_or(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _contains_nonfinite(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(_contains_nonfinite(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_nonfinite(v) for v in value)
    return False


def _issue(
    code: str,
    severity: Severity,
    path: str,
    message: str,
    entity_id: str | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        code,
        severity,
        path,
        message,
        "Inspect and regenerate the package from canonical Forge inputs.",
        entity_id,
    )


def _report(issues: list[ValidationIssue]) -> dict[str, Any]:
    counts = {
        "info": sum(issue.severity == "info" for issue in issues),
        "warning": sum(issue.severity == "warning" for issue in issues),
        "error": sum(issue.severity == "error" for issue in issues),
        "fatal": sum(issue.severity == "fatal" for issue in issues),
    }
    return {
        "schemaVersion": 1,
        "status": "failed" if counts["error"] or counts["fatal"] else "passed",
        "counts": counts,
        "issues": [issue.to_json() for issue in issues],
    }
