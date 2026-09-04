from __future__ import annotations

from collections import Counter
from typing import Any

from . import PROTOCOL_ID
from .common import canonical_digest

MODES = ("A", "B", "C", "D", "E")
FAMILIES = ("tshirt", "sleeveless_top", "simple_skirt")
STRATA = ("in_model", "cross_generator")
CONTROL_NAMES = (
    "localized_source_pixel_intervention",
    "evaluator_hidden_target_mutation",
    "estimated_camera_perturbation",
    "visibility_occlusion_perturbation",
    "association_mismatch",
)


def build_protocol() -> dict[str, Any]:
    sessions = _session_plan()
    thresholds = _threshold_registry()
    denominators = {
        "attemptedSessions": 90,
        "developmentSessions": 60,
        "lockedSessions": 30,
        "lockedSessionsPerMode": 6,
        "lockedSessionsPerFamily": 10,
        "lockedSessionsPerModeFamilyCell": 2,
        "lockedStrataPerModeFamilyCell": list(STRATA),
        "lockedAppearanceControlOutcomes": 150,
        "appearanceControlsPerLockedSession": 5,
    }
    candidate_budget = {
        "maximumTrainingPasses": 1,
        "maximumModelSelectionPasses": 1,
        "maximumFitCandidatesPerSession": 12,
        "maximumFitIterationsPerCandidate": 4,
        "maximumSecondsPerSession": 30,
        "canonicalD0CandidateBudgetConsumed": False,
    }
    protocol: dict[str, Any] = {
        "schemaVersion": 2,
        "protocolId": PROTOCOL_ID,
        "protocolVersion": "closy.source_guarded_capture_reconstruction.v2",
        "evidenceClass": "source_guarded_project_authored_synthetic_capture_engineering",
        "sessionPlan": sessions,
        "denominators": denominators,
        "captureModes": {
            "A": "flat_or_hung_with_rendered_scale_target_and_distinct_geometry",
            "B": "worn_synthetic_avatar_with_body_pose_and_occluder_pixels",
            "C": "synchronised_multiview_with_distinct_intrinsics_extrinsics_and_weak_view",
            "D": "ordered_dynamic_worn_avi_with_pose_camera_and_cloth_motion",
            "E": "weak_single_view_with_ranked_hidden_geometry_hypotheses",
        },
        "contestantVisibleFields": [
            "sourceBytes",
            "coarseCaptureMode",
            "declaredCalibrationTargetType",
            "userCorrections",
        ],
        "evaluatorOnlyFields": [
            "producerIdentity",
            "seed",
            "groundTruthMasks",
            "landmarks",
            "camera",
            "bodyPose",
            "targetParameters",
            "targetMesh",
            "targetUv",
            "targetTexture",
        ],
        "sourceRequirements": {
            "minimumShortestEdgePixels": 256,
            "videoContainer": "RIFF_AVI",
            "videoCodec": "MJPG",
            "minimumDecodedVideoFrames": 24,
            "minimumDistinctVideoFrames": 24,
            "minimumAviClipCount": 12,
            "lockedModeDClipCount": 6,
            "lockedModeDFrames": 144,
        },
        "artifactBudget": {
            "frozenBeforeCorpus": True,
            "maximumOwnLayerBytes": 64 * 1024 * 1024,
            "maximumSourceFileBytes": 512 * 1024,
            "maximumRetainedFiles": 850,
            "stillCodecQuality": 82,
            "videoJpegQuality": 58,
            "contentAddressedDeduplication": "sha256_exact_bytes",
            "rawVideoFramesRetainedSeparately": False,
        },
        "candidateBudget": candidate_budget,
        "executionRegistry": {
            "thresholds": [
                {
                    "id": row["id"],
                    "metric": row["metric"],
                    "evaluatorFunction": row["evaluatorFunction"],
                }
                for row in thresholds
            ],
            "denominators": [
                {
                    "id": key,
                    "expected": value,
                    "evaluatorFunction": f"validate_denominator_{key}",
                }
                for key, value in denominators.items()
            ],
            "stoppingRules": [
                {
                    "id": key,
                    "limit": value,
                    "evaluatorFunction": f"enforce_budget_{key}",
                }
                for key, value in candidate_budget.items()
            ],
        },
        "splitPolicy": {
            "sharedGarmentGrammarAllowed": True,
            "exactAssetOverlapAllowed": False,
            "seedOverlapAllowed": False,
            "identityOverlapAllowed": False,
            "renderTemplateOverlapAllowed": False,
            "lockedTruthWithheldUntilAtomicResult": True,
            "lockedIdentitiesSingleUse": True,
        },
        "coordinateConvention": {
            "world": "right_handed_x_right_y_up_z_toward_camera",
            "image": "x_right_y_down_pixel_centers",
            "camera": "camera_to_world_rotation_translation",
            "scaleGauge": (
                "rendered_checker_target_0.20m_when_detected_else_relative_with_uncertainty"
            ),
        },
        "thresholdRegistry": thresholds,
        "acceptance": {
            "minimumOverallIntrinsicPackageValidity": 0.90,
            "minimumPerFamilyIntrinsicPackageValidity": 0.80,
            "allModeFamilyHardGatesMustPass": True,
            "unusedOrUndeclaredMetricFails": True,
            "firstUnmetPredicateOrder": [row["id"] for row in thresholds],
        },
        "terminalFailureTaxonomy": [
            "passed",
            "failed",
            "abstained",
            "qc_rejected",
            "timeout",
            "crash",
            "invalid_package",
            "physically_invalid",
            "non_finite",
            "integrity_error",
            "unsupported",
            "not_run",
        ],
        "appearanceControls": list(CONTROL_NAMES),
        "singleUseEvaluation": True,
        "postObservationChangesRequire": "future_v3_new_corpus",
        "realCapture": "not_run",
        "privateUserEvidence": "not_run",
        "d0Qualification": "not_run",
        "productAcceptance": False,
    }
    protocol["protocolDigest"] = canonical_digest(protocol)
    return protocol


def validate_protocol(protocol: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    plan = protocol.get("sessionPlan")
    if not isinstance(plan, list) or len(plan) != 90:
        failures.append("protocol_session_denominator_invalid")
        return failures
    ids = [str(row.get("sessionId", "")) for row in plan]
    ordinals = [int(row.get("planOrdinal", -1)) for row in plan]
    if len(ids) != len(set(ids)) or sorted(ordinals) != list(range(90)):
        failures.append("protocol_session_identity_or_ordinal_invalid")
    partition = Counter(str(row.get("partition")) for row in plan)
    if partition != Counter({"development": 60, "locked": 30}):
        failures.append("protocol_partition_counts_invalid")
    locked = [row for row in plan if row.get("partition") == "locked"]
    cells = Counter((str(row.get("mode")), str(row.get("family"))) for row in locked)
    expected_cells = {(mode, family): 2 for mode in MODES for family in FAMILIES}
    if dict(cells) != expected_cells:
        failures.append("protocol_locked_cell_denominator_invalid")
    for mode, family in expected_cells:
        strata = {
            str(row.get("stratum"))
            for row in locked
            if row.get("mode") == mode and row.get("family") == family
        }
        if strata != set(STRATA):
            failures.append("protocol_locked_cell_strata_invalid")
    registry = protocol.get("thresholdRegistry")
    if not isinstance(registry, list) or not registry:
        failures.append("protocol_threshold_registry_missing")
    else:
        threshold_ids = [str(row.get("id", "")) for row in registry]
        metric_names = [str(row.get("metric", "")) for row in registry]
        if len(threshold_ids) != len(set(threshold_ids)) or "" in threshold_ids:
            failures.append("protocol_threshold_id_duplicate_or_missing")
        if len(metric_names) != len(set(metric_names)) or "" in metric_names:
            failures.append("protocol_metric_duplicate_or_missing")
        if any(not row.get("evaluatorFunction") for row in registry):
            failures.append("protocol_threshold_evaluator_binding_missing")
    execution = protocol.get("executionRegistry")
    if not isinstance(execution, dict):
        failures.append("protocol_execution_registry_missing")
    else:
        threshold_bindings = execution.get("thresholds", [])
        denominator_bindings = execution.get("denominators", [])
        stopping_bindings = execution.get("stoppingRules", [])
        if {
            (str(row.get("id")), str(row.get("metric")), str(row.get("evaluatorFunction")))
            for row in threshold_bindings
        } != {
            (str(row.get("id")), str(row.get("metric")), str(row.get("evaluatorFunction")))
            for row in protocol.get("thresholdRegistry", [])
        }:
            failures.append("protocol_threshold_execution_registry_mismatch")
        if {
            (str(row.get("id")), _registry_value(row.get("expected")))
            for row in denominator_bindings
        } != {
            (str(key), _registry_value(value))
            for key, value in protocol.get("denominators", {}).items()
        } or any(not row.get("evaluatorFunction") for row in denominator_bindings):
            failures.append("protocol_denominator_execution_registry_mismatch")
        if {
            (str(row.get("id")), _registry_value(row.get("limit"))) for row in stopping_bindings
        } != {
            (str(key), _registry_value(value))
            for key, value in protocol.get("candidateBudget", {}).items()
        } or any(not row.get("evaluatorFunction") for row in stopping_bindings):
            failures.append("protocol_stopping_execution_registry_mismatch")
    if protocol.get("protocolDigest") != canonical_digest(protocol, "protocolDigest"):
        failures.append("protocol_digest_invalid")
    return sorted(set(failures))


def _registry_value(value: Any) -> str:
    return repr(value)


def _session_plan() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ordinal = 0
    for partition, per_cell in (("development", 4), ("locked", 2)):
        for mode_index, mode in enumerate(MODES):
            for family_index, family in enumerate(FAMILIES):
                for cell_index in range(per_cell):
                    if partition == "locked":
                        stratum = STRATA[cell_index]
                    else:
                        stratum = STRATA[(cell_index + mode_index + family_index) % 2]
                    rows.append(
                        {
                            "sessionId": f"capv2-{partition[:3]}-{ordinal:03d}",
                            "partition": partition,
                            "mode": mode,
                            "family": family,
                            "stratum": stratum,
                            "presentation": "flat"
                            if mode == "A" and cell_index % 2 == 0
                            else "hung",
                            # This ordinal controls scheduling only. It is never a render seed.
                            "planOrdinal": ordinal,
                            "resolution": [
                                256 + 32 * ((ordinal + family_index) % 3),
                                256 + 32 * ((ordinal + mode_index) % 2),
                            ],
                            "weakOrMissingViewIndex": 2 if mode == "C" else None,
                            "expectedSourceCount": 3 if mode == "C" else 1,
                            "expectedVideoFrames": 24 if mode == "D" else 0,
                        }
                    )
                    ordinal += 1
    return rows


def _threshold_registry() -> list[dict[str, Any]]:
    rows = (
        ("qc.decode_rate", "minimum", 1.0, "metric_decode_rate"),
        ("qc.accepted_rate", "minimum", 0.70, "metric_accepted_rate"),
        ("segmentation.garment_iou", "minimum", 0.62, "metric_garment_iou"),
        ("segmentation.boundary_fscore", "minimum", 0.50, "metric_boundary_fscore"),
        ("segmentation.part_accuracy", "minimum", 0.55, "metric_part_accuracy"),
        ("landmarks.normalized_error", "maximum", 0.16, "metric_landmark_error"),
        ("camera.rotation_degrees", "maximum", 24.0, "metric_camera_rotation"),
        ("camera.focal_relative_error", "maximum", 0.30, "metric_focal_error"),
        ("camera.principal_point_error", "maximum", 0.12, "metric_principal_error"),
        ("camera.scale_relative_error", "maximum", 0.25, "metric_scale_error"),
        ("camera.reprojection_pixels", "maximum", 22.0, "metric_reprojection"),
        ("body.pose_normalized_error", "maximum", 0.22, "metric_body_pose"),
        ("fit.silhouette_error", "maximum", 0.35, "metric_fit_silhouette"),
        ("fit.seam_relative_error", "maximum", 0.18, "metric_fit_seam"),
        ("fit.body_clearance_error", "maximum", 0.25, "metric_body_clearance"),
        ("fit.temporal_drift", "maximum", 0.20, "metric_temporal_drift"),
        ("package.overall_validity", "minimum", 0.90, "metric_package_overall"),
        ("package.family_validity", "minimum", 0.80, "metric_package_family"),
        ("appearance.delta_e_proxy", "maximum", 0.34, "metric_appearance_color"),
        ("appearance.ssim_proxy", "minimum", 0.60, "metric_appearance_structure"),
        ("appearance.visible_texel_coverage", "minimum", 0.45, "metric_texel_coverage"),
        ("video.distinct_frame_rate", "minimum", 1.0, "metric_video_distinct_frames"),
        ("video.temporal_consistency", "minimum", 0.55, "metric_video_temporal"),
        ("mode_e.hypothesis_coverage", "minimum", 0.66, "metric_hypothesis_coverage"),
        ("controls.pass_rate", "minimum", 1.0, "metric_control_pass_rate"),
        ("privacy.integrity_pass", "minimum", 1.0, "metric_privacy_integrity"),
    )
    return [
        {
            "id": f"CAPV2-{index + 1:02d}",
            "metric": metric,
            "direction": direction,
            "limit": limit,
            "evaluatorFunction": function,
            "hardScope": "session_or_cell" if index < 16 else "global_or_family",
            "source": "development_distribution_and_blueprint_business_tolerance",
        }
        for index, (metric, direction, limit, function) in enumerate(rows)
    ]
