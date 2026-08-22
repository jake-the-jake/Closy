from __future__ import annotations

import math
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
from closy_forge.package_io.canonical_json import read_json
from closy_forge.package_io.hashing import geometry_content_hash, sha256_file, topology_hash
from closy_forge.package_io.paths import validate_package_relpath
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
