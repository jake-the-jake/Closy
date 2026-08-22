from __future__ import annotations

import math
import tempfile
from pathlib import Path
from typing import Any

from closy_forge.appearance import hash_texture_identity_report
from closy_forge.binding.binary_format import read_binding
from closy_forge.binding.reconstruct import reconstruct_vertices, reconstruction_error
from closy_forge.capture.source_records import hash_capture_record
from closy_forge.contracts.avatar import REQUIRED_BODY_REGIONS, REQUIRED_LANDMARKS
from closy_forge.contracts.common import COORDINATE_CONVENTION
from closy_forge.contracts.semantic import REQUIRED_OPENINGS, REQUIRED_PANELS, REQUIRED_SEAMS
from closy_forge.fitting import hash_tshirt_fit_report
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.geometry.curves import sample_curve
from closy_forge.geometry.glb_io import audit_glb
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
from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import (
    geometry_content_hash,
    sha256_bytes,
    sha256_file,
    topology_hash,
)
from closy_forge.package_io.paths import validate_package_relpath
from closy_forge.proposals import (
    PARTIAL_BINDING_VALIDATION_REJECTION_REASONS,
    PARTIAL_CLEANUP_REJECTION_REASONS,
    PARTIAL_REPAIR_RETOPOLOGY_PLAN_REJECTION_REASONS,
    PARTIAL_SEMANTIC_TRANSFER_REJECTION_REASONS,
    REQUIRED_CLEAN_REJECTION_REASONS,
    build_geometry_binding_candidate_report,
    build_geometry_binding_validation_report,
    build_geometry_cleanup_plan,
    build_geometry_cleanup_result,
    build_geometry_repair_retopology_plan,
    build_geometry_semantic_transfer_report,
    build_raw_geometry_topology_report,
    hash_clean_geometry_proposal,
    hash_geometry_binding_candidate_report,
    hash_geometry_binding_validation_report,
    hash_geometry_cleanup_plan,
    hash_geometry_cleanup_result,
    hash_geometry_proposal,
    hash_geometry_repair_retopology_plan,
    hash_geometry_semantic_transfer_report,
    hash_provider_registry,
    hash_raw_geometry_topology_report,
)
from closy_forge.validation.issues import Severity, ValidationIssue
from closy_forge.visual_understanding import (
    REQUIRED_TSHIRT_VISUAL_LANDMARKS,
    hash_correction_record,
    hash_visual_observations,
)

EXPECTED_FILES = [
    "manifest.json",
    "provenance.json",
    "source/capture_record.json",
    "source/capture_quality.json",
    "source/visual_observations.json",
    "source/correction_record.json",
    "fitting/tshirt_fit.json",
    "textures/texture_identity.json",
    "proposals/raw_geometry_proposal.json",
    "proposals/manual_raw_visual_proposal.glb",
    "proposals/manual_cleanup_preview.glb",
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
    "render/fallback.glb",
    "render/mesh_manifest.json",
    "render/materials.json",
    "binding/sim_to_render.bin",
    "binding/binding_manifest.json",
    "reports/avatar_quality.json",
    "reports/capture_quality.json",
    "reports/visual_understanding_quality.json",
    "reports/fitting_quality.json",
    "reports/texture_quality.json",
    "reports/geometry_proposal_quality.json",
    "reports/raw_geometry_topology.json",
    "reports/geometry_cleanup_plan.json",
    "reports/geometry_cleanup_result.json",
    "reports/geometry_semantic_transfer.json",
    "reports/geometry_binding_candidate.json",
    "reports/geometry_binding_validation.json",
    "reports/geometry_repair_retopology_plan.json",
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
    _validate_fitting(package_dir, manifest, issues)
    _validate_texture_identity(package_dir, manifest, issues)
    _validate_geometry_proposal(package_dir, manifest, issues)
    _validate_raw_geometry_topology(package_dir, manifest, issues)
    _validate_geometry_cleanup_plan(package_dir, manifest, issues)
    _validate_geometry_cleanup_result(package_dir, manifest, issues)
    _validate_geometry_semantic_transfer(package_dir, manifest, issues)
    _validate_geometry_binding_candidate(package_dir, manifest, issues)
    _validate_geometry_binding_validation(package_dir, manifest, issues)
    _validate_geometry_repair_retopology_plan(package_dir, manifest, issues)
    _validate_provider_registry(package_dir, manifest, issues)
    _validate_clean_geometry_proposal(package_dir, manifest, issues)
    _validate_semantic(package_dir, issues)
    _validate_pattern(package_dir, issues)
    _validate_meshes_and_constraints(package_dir, issues)
    _validate_settle_state(package_dir, manifest, issues)
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


def _validate_fitting(
    package_dir: Path, manifest: dict[str, Any], issues: list[ValidationIssue]
) -> None:
    visual = _read_required_json(package_dir, "source/visual_observations.json", issues)
    fit_report = _read_required_json(package_dir, "fitting/tshirt_fit.json", issues)
    if visual is None or fit_report is None:
        return
    declared_visual_hash = _nested_string(visual, ["integrity", "visualRecordHash"], "")
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
            TShirtParameters(**{key: float(value) for key, value in fitted_parameters.items()})
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
    fit_report = _read_required_json(package_dir, "fitting/tshirt_fit.json", issues)
    render_materials = _read_required_json(package_dir, "render/materials.json", issues)
    texture = _read_required_json(package_dir, "textures/texture_identity.json", issues)
    texture_quality = _read_required_json(package_dir, "reports/texture_quality.json", issues)
    if (
        capture_record is None
        or visual is None
        or fit_report is None
        or render_materials is None
        or texture is None
    ):
        return
    declared_capture_hash = _nested_string(capture_record, ["immutability", "sourceRecordHash"], "")
    declared_visual_hash = _nested_string(visual, ["integrity", "visualRecordHash"], "")
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
    if (
        texture.get("sourceTextureAvailable") is not False
        or texture.get("generatedAtlasAvailable") is not False
        or texture.get("textureProjectionRun") is not False
    ):
        issues.append(
            _issue(
                "texture_identity_source_state_invalid",
                "fatal",
                "textures/texture_identity.json",
                "Implementation 04 texture identity must not claim source texture projection.",
            )
        )
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
    if (
        texture.get("sourceTextureAvailable") is False
        and caps.get("sourceImageTextureAvailable") is not False
    ):
        issues.append(
            _issue(
                "texture_source_capability_contradiction",
                "fatal",
                "manifest.json",
                "sourceImageTextureAvailable must remain false without source texture evidence.",
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
    provider_ids = {
        str(provider.get("providerId", "")) for provider in providers if isinstance(provider, dict)
    }
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
        provider_policy = provider.get("policy", {})
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
                    str(provider.get("providerId", "")),
                )
            )
        if (
            provider_policy.get("approvedDomain") != "avatar_and_garment_only"
            or provider_policy.get("allowsGenericObjects") is not False
            or "garment_visual_geometry_proposal" not in provider.get("supportedPurposes", [])
            or manifest.get("garmentClass") not in provider.get("supportedGarmentClasses", [])
        ):
            issues.append(
                _issue(
                    "provider_registry_provider_domain_invalid",
                    "fatal",
                    "proposals/provider_registry.json",
                    "Provider entries must be garment/avatar constrained.",
                    str(provider.get("providerId", "")),
                )
            )

    manual_asset_available = manual.get("acceptedForRawProposal") is True
    expected_d0 = [
        ("providerRegistryAvailable", True),
        ("nullProviderAvailable", True),
        ("manualLocalImportAdapterDeclared", True),
        ("manualLocalImportAssetAvailable", manual_asset_available),
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
            ("manualGeometryImportAdapterDeclared", True),
            ("manualGeometryImportAssetAvailable", manual_asset_available),
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
    if cleanup.get("simulationBindingRun") != binding_execution.get("simulationBindingRun"):
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_state_invalid",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal simulationBindingRun must mirror the binding candidate report.",
            )
        )
    validation_execution = binding_validation.get("execution", {})
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
    if cleanup.get("runtimeBindingAccepted") != validation_execution.get("runtimeBindingAccepted"):
        issues.append(
            _issue(
                "clean_geometry_proposal_cleanup_state_invalid",
                "fatal",
                "proposals/clean_geometry_proposal.json",
                "Clean proposal runtimeBindingAccepted must mirror the binding validation report.",
            )
        )
    for key in [
        "repairRun",
        "retopologyRun",
        "uvTransferRun",
        "materialTransferRun",
        "seamSplitRun",
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
                    "repair/retopology plan."
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


def _validate_glbs(package_dir: Path, issues: list[ValidationIssue]) -> None:
    for rel in [
        "avatar/reference_avatar.glb",
        "avatar/collision.glb",
        "simulation/simulation_mesh.glb",
        "render/fallback.glb",
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
                "Reference solver v1 does not implement self-collision.",
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
