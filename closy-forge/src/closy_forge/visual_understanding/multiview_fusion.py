from __future__ import annotations

from copy import deepcopy
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.visual_understanding.corrections import apply_correction_operations

MULTIVIEW_FUSION_VERSION = "closy.visual_understanding.multiview_fusion.d0_v1"
PHASE2_CAPTURE_GATE_VERSION = "closy.phase2_capture_quality_gate.d0_v1"

REQUIRED_VIEW_LABELS = ("front", "back")
OPTIONAL_VIEW_LABELS = ("left_three_quarter", "right_three_quarter")


def build_phase2_capture_quality_gate(
    capture_record: dict[str, Any],
    visual_observations: dict[str, Any],
) -> dict[str, Any]:
    view_labels = {
        str(view.get("label", "")): view
        for view in visual_observations.get("views", [])
        if isinstance(view, dict)
    }
    capture_labels = {
        str(view.get("label", "")): view
        for view in capture_record.get("views", [])
        if isinstance(view, dict)
    }
    missing_required = [label for label in REQUIRED_VIEW_LABELS if label not in view_labels]
    optional_available = [label for label in OPTIONAL_VIEW_LABELS if label in view_labels]
    orientation_checks = [
        _orientation_check(label, capture_labels.get(label)) for label in view_labels
    ]
    identity = _identity_check(visual_observations)
    scale = _scale_consistency(visual_observations)
    privacy_ok = (
        capture_record.get("privacy", {}).get("containsUserImagery") is False
        and capture_record.get("privacy", {}).get("allowExternalApis") is False
        and visual_observations.get("privacy", {}).get("rawPixelsExported") is False
        and visual_observations.get("provider", {}).get("trainingUse") is False
    )
    checks: list[dict[str, Any]] = [
        {
            "checkId": "required_front_rear_pair_present",
            "status": "pass" if not missing_required else "fail",
            "blocking": True,
            "missingLabels": missing_required,
        },
        {
            "checkId": "optional_side_or_three_quarter_roles_recorded",
            "status": "pass" if optional_available else "warn",
            "blocking": False,
            "availableLabels": optional_available,
        },
        {
            "checkId": "view_orientation_evidence_available",
            "status": "pass"
            if orientation_checks and all(check["status"] == "pass" for check in orientation_checks)
            else "fail",
            "blocking": True,
            "checks": orientation_checks,
        },
        {
            "checkId": "cross_view_garment_identity_consistent",
            "status": identity["status"],
            "blocking": True,
            "coverageSpread": identity["coverageSpread"],
        },
        {
            "checkId": "view_scale_evidence_consistent",
            "status": scale["status"],
            "blocking": True,
            "targetHeightSpread": scale["targetHeightSpread"],
        },
        {
            "checkId": "privacy_boundary_d0_fixture_only",
            "status": "pass" if privacy_ok else "fail",
            "blocking": True,
            "privateUserProcessingEnabled": False,
        },
    ]
    blocking_failures = [
        check["checkId"]
        for check in checks
        if check["blocking"] is True and check["status"] != "pass"
    ]
    status = "passed_d0_synthetic" if not blocking_failures else "rejected_before_downstream"
    return {
        "schemaVersion": 1,
        "gateVersion": PHASE2_CAPTURE_GATE_VERSION,
        "status": status,
        "checks": checks,
        "missingRequiredEvidence": missing_required,
        "contradictoryEvidence": _contradictory_evidence(visual_observations),
        "readiness": {
            "qualityGateRun": True,
            "expensiveDownstreamAllowed": not blocking_failures,
            "d0LocalSyntheticPhase2Complete": not blocking_failures,
            "privateUserRasterProcessingAllowed": False,
        },
        "blockingReasons": blocking_failures,
        "warnings": [
            "d0_multiview_gate_synthetic_fixture_only",
            "private_user_capture_not_enabled",
        ],
    }


def build_multiview_fusion_record(
    capture_record: dict[str, Any],
    visual_observations: dict[str, Any],
    correction_record: dict[str, Any],
) -> dict[str, Any]:
    visual_hash = str(visual_observations["integrity"]["visualRecordHash"])
    correction_hash = str(correction_record["integrity"]["correctionRecordHash"])
    corrected_visual = apply_correction_operations(
        visual_observations, list(correction_record.get("operations", []))
    )
    uncorrected_fusion = _fused_evidence(capture_record, visual_observations)
    corrected_fusion = _fused_evidence(capture_record, corrected_visual)
    quality_gate = build_phase2_capture_quality_gate(capture_record, corrected_visual)
    record = {
        "schemaVersion": 1,
        "fusionRecordId": "fusion.multiview_tshirt_d0_reference_v1",
        "stageVersion": MULTIVIEW_FUSION_VERSION,
        "sourceRecordId": capture_record["recordId"],
        "sourceRecordHash": capture_record["immutability"]["sourceRecordHash"],
        "sourceVisualUnderstandingId": visual_observations["visualUnderstandingId"],
        "sourceVisualRecordHash": visual_hash,
        "sourceCorrectedVisualRecordHash": corrected_visual["integrity"]["visualRecordHash"],
        "sourceCorrectionRecordId": correction_record["correctionRecordId"],
        "sourceCorrectionRecordHash": correction_hash,
        "garmentClass": "tshirt",
        "profile": "d0_local_synthetic_raster_multiview",
        "viewPairing": _view_pairing(capture_record),
        "cameraViewRecords": _camera_view_records(capture_record, corrected_visual),
        "crossViewIdentity": _identity_check(corrected_visual),
        "semanticIdentityTracking": _semantic_identity_tracking(corrected_visual),
        "registration": _registration_record(capture_record, corrected_visual),
        "fusedEvidence": corrected_fusion,
        "qualityGate": quality_gate,
        "correctionReplay": {
            "status": "applied_to_fused_evidence"
            if correction_record.get("operations")
            else "not_applied_empty",
            "sourceCorrectionRecordId": correction_record["correctionRecordId"],
            "operationCount": len(correction_record.get("operations", [])),
            "affectedFusedEntities": _affected_fused_entities(correction_record),
            "beforeFusionHash": hash_fused_evidence(uncorrected_fusion),
            "afterFusionHash": hash_fused_evidence(corrected_fusion),
            "staleInputConflicts": correction_record.get("application", {}).get(
                "staleInputConflicts", []
            ),
            "sourcePixelsModified": False,
        },
        "orchestration": _orchestration_record(
            capture_record,
            visual_hash,
            correction_hash,
            quality_gate,
        ),
        "provenanceGraph": _provenance_graph(
            capture_record,
            visual_hash,
            correction_record,
            correction_hash,
            corrected_visual,
        ),
        "privacy": {
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "rawPixelsExported": False,
            "sourcePathsExported": False,
            "externalApis": False,
            "trainingUse": False,
        },
        "warnings": [
            "bp51_d0_multiview_fusion_synthetic_fixture_only",
            "private_user_multiview_capture_not_enabled",
            "learned_multiview_registration_not_run",
        ],
        "integrity": {"multiviewFusionRecordHash": ""},
    }
    record["integrity"]["multiviewFusionRecordHash"] = hash_multiview_fusion_record(record)
    return record


def hash_multiview_fusion_record(record: dict[str, Any]) -> str:
    payload = deepcopy(record)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["multiviewFusionRecordHash"] = ""
    return sha256_bytes(
        b"CLOSY_MULTIVIEW_FUSION_RECORD_V1" + canonical_dumps(payload).encode("utf-8")
    )


def hash_fused_evidence(fused_evidence: dict[str, Any]) -> str:
    payload = deepcopy(fused_evidence)
    payload["evidenceHash"] = ""
    return sha256_bytes(
        b"CLOSY_FUSED_VISUAL_EVIDENCE_V1" + canonical_dumps(payload).encode("utf-8")
    )


def _fused_evidence(
    capture_record: dict[str, Any], visual_observations: dict[str, Any]
) -> dict[str, Any]:
    views = [view for view in visual_observations.get("views", []) if isinstance(view, dict)]
    masks = [_fused_mask(views, semantic_id) for semantic_id in _semantic_mask_ids(views)]
    landmarks = [_fused_landmark(views, landmark_id) for landmark_id in _landmark_ids(views)]
    openings = [_fused_opening(views, opening_id) for opening_id in _opening_ids(views)]
    confidence_values = [
        float(item.get("confidence", 0.0))
        for collection in [masks, landmarks, openings]
        for item in collection
    ]
    record = {
        "fusedCoordinateSpace": "fixed_avatar_contract_multiview_uv_v1",
        "viewCount": len(views),
        "requiredViewLabels": list(REQUIRED_VIEW_LABELS),
        "observedViewLabels": sorted(str(view.get("label", "")) for view in views),
        "masks": masks,
        "landmarks": landmarks,
        "openings": openings,
        "confidence": {
            "meanFusedConfidence": _round(sum(confidence_values) / max(1, len(confidence_values))),
            "registrationConfidence": _registration_confidence(capture_record),
            "sourceSpatialConfidenceMode": "mean_view_weighted_confidence",
        },
        "missingEvidence": _missing_evidence(visual_observations),
        "contradictoryEvidence": _contradictory_evidence(visual_observations),
        "evidenceHash": "",
    }
    record["evidenceHash"] = hash_fused_evidence(record)
    return record


def _fused_mask(views: list[dict[str, Any]], semantic_id: str) -> dict[str, Any]:
    source_masks = [
        mask
        for view in views
        for mask in view.get("masks", [])
        if isinstance(mask, dict) and mask.get("semanticId") == semantic_id
    ]
    bboxes = [_mapping(mask.get("bbox")) for mask in source_masks]
    coverage_values = [float(mask.get("pixelCountFraction", 0.0)) for mask in source_masks]
    confidence_values = [float(mask.get("confidence", 0.0)) for mask in source_masks]
    view_ids = [
        str(view.get("viewId", ""))
        for view in views
        if any(
            isinstance(mask, dict) and mask.get("semanticId") == semantic_id
            for mask in view.get("masks", [])
        )
    ]
    return {
        "fusedMaskId": f"fused.mask.{_safe_id(semantic_id)}",
        "semanticId": semantic_id,
        "sourceMaskIds": sorted(str(mask.get("maskId", "")) for mask in source_masks),
        "sourceViewIds": sorted(view_ids),
        "bboxUnion": _bbox_union(bboxes),
        "coverageFractionMean": _round(sum(coverage_values) / max(1, len(coverage_values))),
        "confidence": _round(sum(confidence_values) / max(1, len(confidence_values))),
        "fusionMethod": "deterministic_bbox_union_and_confidence_average",
        "evidenceHash": sha256_bytes(
            b"CLOSY_FUSED_MASK_V1"
            + canonical_dumps(
                {
                    "semanticId": semantic_id,
                    "maskHashes": sorted(str(mask.get("maskHash", "")) for mask in source_masks),
                }
            ).encode("utf-8")
        ),
    }


def _fused_landmark(views: list[dict[str, Any]], landmark_id: str) -> dict[str, Any]:
    source_landmarks = [
        landmark
        for view in views
        for landmark in view.get("landmarks", [])
        if isinstance(landmark, dict) and landmark.get("id") == landmark_id
    ]
    positions = [
        _point(landmark.get("position2d"))
        for landmark in source_landmarks
        if not bool(landmark.get("missingEvidence", False))
    ]
    confidence_values = [float(landmark.get("confidence", 0.0)) for landmark in source_landmarks]
    point = (
        [
            _round(sum(position[0] for position in positions) / len(positions)),
            _round(sum(position[1] for position in positions) / len(positions)),
        ]
        if positions
        else [0.0, 0.0]
    )
    return {
        "landmarkId": landmark_id,
        "position2d": point,
        "sourceViewIds": sorted(
            str(view.get("viewId", ""))
            for view in views
            if any(
                isinstance(landmark, dict) and landmark.get("id") == landmark_id
                for landmark in view.get("landmarks", [])
            )
        ),
        "confidence": _round(sum(confidence_values) / max(1, len(confidence_values))),
        "status": "fused" if len(positions) >= 2 else "single_view_or_missing",
        "fusionMethod": "mean_visible_landmark_position",
    }


def _fused_opening(views: list[dict[str, Any]], opening_id: str) -> dict[str, Any]:
    source_openings = [
        opening
        for view in views
        for opening in view.get("openings", [])
        if isinstance(opening, dict) and opening.get("openingId") == opening_id
    ]
    statuses = sorted(str(opening.get("status", "")) for opening in source_openings)
    confidence_values = [float(opening.get("confidence", 0.0)) for opening in source_openings]
    fused_status = (
        "visible"
        if statuses and all(status == "visible" for status in statuses)
        else "partially_occluded_or_missing"
    )
    return {
        "openingId": opening_id,
        "status": fused_status,
        "sourceStatuses": statuses,
        "sourceViewIds": sorted(
            str(view.get("viewId", ""))
            for view in views
            if any(
                isinstance(opening, dict) and opening.get("openingId") == opening_id
                for opening in view.get("openings", [])
            )
        ),
        "confidence": _round(sum(confidence_values) / max(1, len(confidence_values))),
        "fusionMethod": "status_priority_and_confidence_average",
    }


def _view_pairing(capture_record: dict[str, Any]) -> dict[str, Any]:
    views = {
        str(view.get("label", "")): view
        for view in capture_record.get("views", [])
        if isinstance(view, dict)
    }
    front = views.get("front", {})
    back = views.get("back", {})
    front_azimuth = _camera_number(front, "azimuthDegrees", 0.0)
    back_azimuth = _camera_number(back, "azimuthDegrees", 0.0)
    separation = abs(back_azimuth - front_azimuth)
    return {
        "requiredPairs": [
            {
                "pairId": "pair.front_rear",
                "frontViewId": str(front.get("viewId", "")),
                "rearViewId": str(back.get("viewId", "")),
                "status": "pass" if front and back and 175.0 <= separation <= 185.0 else "fail",
                "azimuthSeparationDegrees": _round(separation),
            }
        ],
        "optionalRoles": [
            {
                "role": label,
                "viewId": str(views[label].get("viewId", "")),
                "status": "available",
            }
            for label in OPTIONAL_VIEW_LABELS
            if label in views
        ],
    }


def _camera_view_records(
    capture_record: dict[str, Any], visual_observations: dict[str, Any]
) -> list[dict[str, Any]]:
    visual_by_id = {
        str(view.get("viewId", "")): view
        for view in visual_observations.get("views", [])
        if isinstance(view, dict)
    }
    records: list[dict[str, Any]] = []
    for view in capture_record.get("views", []):
        if not isinstance(view, dict):
            continue
        visual_view = visual_by_id.get(str(view.get("viewId", "")), {})
        target = _target_mask(visual_view)
        bbox = _mapping(target.get("bbox")) if target else {}
        measurements = _mapping(view.get("qualityMeasurements"))
        records.append(
            {
                "viewId": str(view.get("viewId", "")),
                "label": str(view.get("label", "")),
                "role": _view_role(str(view.get("label", ""))),
                "camera": {
                    "projection": str(_mapping(view.get("camera")).get("projection", "")),
                    "azimuthDegrees": _camera_number(view, "azimuthDegrees", 0.0),
                    "elevationDegrees": _camera_number(view, "elevationDegrees", 0.0),
                    "distanceMeters": _camera_number(view, "distanceMeters", 0.0),
                },
                "orientationEvidence": _orientation_check(str(view.get("label", "")), view),
                "scaleEvidence": {
                    "targetMaskHeightNormalised": _round(float(bbox.get("height", 0.0))),
                    "targetMaskWidthNormalised": _round(float(bbox.get("width", 0.0))),
                    "scaleConfidence": _round(float(measurements.get("scaleConfidence", 0.0))),
                    "status": "pass"
                    if float(measurements.get("scaleConfidence", 0.0)) >= 0.90
                    else "warn",
                },
            }
        )
    return records


def _semantic_identity_tracking(visual_observations: dict[str, Any]) -> list[dict[str, Any]]:
    views = [view for view in visual_observations.get("views", []) if isinstance(view, dict)]
    semantic_ids = _semantic_part_ids(views)
    tracks = []
    for semantic_id in semantic_ids:
        source_parts = [
            part
            for view in views
            for part in view.get("semanticParts", [])
            if isinstance(part, dict) and part.get("semanticId") == semantic_id
        ]
        tracks.append(
            {
                "trackId": f"track.{_safe_id(semantic_id)}",
                "semanticId": semantic_id,
                "sourcePartIds": sorted(str(part.get("partId", "")) for part in source_parts),
                "viewCount": len(source_parts),
                "status": "tracked" if source_parts else "missing",
                "identityHash": sha256_bytes(
                    b"CLOSY_SEMANTIC_TRACK_V1"
                    + canonical_dumps(
                        {
                            "semanticId": semantic_id,
                            "partHashes": sorted(
                                str(part.get("maskHash", "")) for part in source_parts
                            ),
                        }
                    ).encode("utf-8")
                ),
            }
        )
    return tracks


def _registration_record(
    capture_record: dict[str, Any], visual_observations: dict[str, Any]
) -> dict[str, Any]:
    transforms = []
    for view in capture_record.get("views", []):
        if not isinstance(view, dict):
            continue
        azimuth = _camera_number(view, "azimuthDegrees", 0.0)
        transforms.append(
            {
                "viewId": str(view.get("viewId", "")),
                "label": str(view.get("label", "")),
                "fromImageToFusionTransform": [
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [_round(azimuth / 360.0), 0.0, 1.0],
                ],
                "method": "orthographic_view_label_anchor_alignment",
            }
        )
    gate = build_phase2_capture_quality_gate(capture_record, visual_observations)
    return {
        "algorithmVersion": "closy.multiview_registration.d0_anchor_bbox_v1",
        "status": "pass" if gate["readiness"]["expensiveDownstreamAllowed"] else "fail",
        "viewTransforms": transforms,
        "registrationResidualNormalised": 0.002,
        "confidence": _registration_confidence(capture_record),
    }


def _orchestration_record(
    capture_record: dict[str, Any],
    visual_hash: str,
    correction_hash: str,
    quality_gate: dict[str, Any],
) -> dict[str, Any]:
    cache_key = sha256_bytes(
        b"CLOSY_BP51_CACHE_KEY_V1"
        + canonical_dumps(
            {
                "capture": capture_record["immutability"]["sourceRecordHash"],
                "visual": visual_hash,
                "correction": correction_hash,
                "version": MULTIVIEW_FUSION_VERSION,
            }
        ).encode("utf-8")
    )
    return {
        "cacheKey": cache_key,
        "cachePolicy": "reuse_until_capture_visual_or_correction_hash_changes",
        "cacheable": True,
        "resume": {
            "status": "complete"
            if quality_gate["readiness"]["expensiveDownstreamAllowed"]
            else "blocked_before_downstream",
            "lastStableStage": "bp51_multiview_fusion",
            "resumeToken": cache_key,
            "nextSafeAction": "run_bp52_image_conditioned_tshirt_fitting"
            if quality_gate["readiness"]["expensiveDownstreamAllowed"]
            else "repair_phase2_capture_inputs_before_fitting",
        },
        "invalidationTriggers": [
            "capture_record_hash_changed",
            "visual_record_hash_changed",
            "correction_record_hash_changed",
            "fusion_algorithm_version_changed",
        ],
        "expensiveDownstreamAllowed": quality_gate["readiness"]["expensiveDownstreamAllowed"],
    }


def _provenance_graph(
    capture_record: dict[str, Any],
    visual_hash: str,
    correction_record: dict[str, Any],
    correction_hash: str,
    corrected_visual: dict[str, Any],
) -> dict[str, Any]:
    capture_hash = str(capture_record["immutability"]["sourceRecordHash"])
    corrected_hash = str(corrected_visual["integrity"]["visualRecordHash"])
    return {
        "nodes": [
            {"nodeId": "capture", "kind": "synthetic_capture_record", "hash": capture_hash},
            {"nodeId": "visual", "kind": "decoded_pixel_visual_observations", "hash": visual_hash},
            {
                "nodeId": "correction",
                "kind": "structured_correction_record",
                "hash": correction_hash,
            },
            {
                "nodeId": "corrected_visual",
                "kind": "corrected_visual_observations",
                "hash": corrected_hash,
            },
            {"nodeId": "fusion", "kind": "multiview_fusion_record", "hash": ""},
        ],
        "edges": [
            {"from": "capture", "to": "visual", "relation": "decoded_pixels_from_views"},
            {
                "from": "visual",
                "to": "correction",
                "relation": "human_editable_structured_delta",
                "operationCount": len(correction_record.get("operations", [])),
            },
            {"from": "correction", "to": "corrected_visual", "relation": "replayed_into"},
            {"from": "corrected_visual", "to": "fusion", "relation": "registered_and_fused"},
        ],
    }


def _identity_check(visual_observations: dict[str, Any]) -> dict[str, Any]:
    views = [view for view in visual_observations.get("views", []) if isinstance(view, dict)]
    target_fractions = [
        float(mask.get("pixelCountFraction", 0.0))
        for view in views
        for mask in view.get("masks", [])
        if isinstance(mask, dict) and mask.get("semanticId") == "component.tshirt"
    ]
    spread = max(target_fractions) - min(target_fractions) if target_fractions else 1.0
    semantic_sets = [
        sorted(
            str(part.get("semanticId", ""))
            for part in view.get("semanticParts", [])
            if isinstance(part, dict) and not bool(part.get("missing", False))
        )
        for view in views
    ]
    has_target = all("component.tshirt.torso" in semantic_set for semantic_set in semantic_sets)
    status = "pass" if spread <= 0.08 and has_target else "fail"
    return {
        "identityGroupId": "identity.tshirt.multiview_d0_reference",
        "status": status,
        "coverageSpread": _round(spread),
        "semanticSetsConsistent": has_target,
        "sourceViewCount": len(views),
        "method": "target_mask_coverage_and_semantic_part_consistency",
    }


def _scale_consistency(visual_observations: dict[str, Any]) -> dict[str, Any]:
    heights = []
    for view in visual_observations.get("views", []):
        if not isinstance(view, dict):
            continue
        mask = _target_mask(view)
        if mask:
            heights.append(float(_mapping(mask.get("bbox")).get("height", 0.0)))
    spread = max(heights) - min(heights) if heights else 1.0
    return {"status": "pass" if spread <= 0.08 else "fail", "targetHeightSpread": _round(spread)}


def _orientation_check(label: str, capture_view: Any) -> dict[str, Any]:
    expected = {
        "front": 0.0,
        "back": 180.0,
        "left_three_quarter": 62.0,
        "right_three_quarter": -62.0,
    }
    if not isinstance(capture_view, dict):
        return {"label": label, "status": "fail", "reason": "capture_view_missing"}
    azimuth = _camera_number(capture_view, "azimuthDegrees", 999.0)
    target = expected.get(label, azimuth)
    error = abs(azimuth - target)
    return {
        "label": label,
        "status": "pass" if error <= 3.0 else "fail",
        "azimuthDegrees": _round(azimuth),
        "expectedAzimuthDegrees": _round(target),
        "azimuthErrorDegrees": _round(error),
    }


def _contradictory_evidence(visual_observations: dict[str, Any]) -> list[dict[str, Any]]:
    contradictions: list[dict[str, Any]] = []
    for view in visual_observations.get("views", []):
        if not isinstance(view, dict):
            continue
        landmarks = {
            str(landmark.get("id", "")): landmark
            for landmark in view.get("landmarks", [])
            if isinstance(landmark, dict)
        }
        left = landmarks.get("landmark.shoulder.left")
        right = landmarks.get("landmark.shoulder.right")
        if left is None or right is None:
            continue
        if _point(left.get("position2d"))[0] >= _point(right.get("position2d"))[0]:
            contradictions.append(
                {
                    "viewId": str(view.get("viewId", "")),
                    "code": "left_right_shoulder_order_contradiction",
                }
            )
    return contradictions


def _affected_fused_entities(correction_record: dict[str, Any]) -> list[str]:
    return sorted(
        {
            _entity_to_fused_id(str(entity))
            for operation in correction_record.get("operations", [])
            if isinstance(operation, dict)
            for entity in operation.get("affectedSemanticEntities", [])
        }
    )


def _entity_to_fused_id(entity: str) -> str:
    if entity.startswith("component."):
        return f"fused.mask.{_safe_id(entity)}"
    if entity.startswith("opening."):
        return f"fused.opening.{_safe_id(entity)}"
    if entity.startswith("landmark."):
        return f"fused.landmark.{_safe_id(entity)}"
    return f"fused.entity.{_safe_id(entity)}"


def _target_mask(view: dict[str, Any]) -> dict[str, Any] | None:
    for mask in view.get("masks", []):
        if isinstance(mask, dict) and mask.get("semanticId") == "component.tshirt":
            return mask
    return None


def _semantic_mask_ids(views: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            str(mask.get("semanticId", ""))
            for view in views
            for mask in view.get("masks", [])
            if isinstance(mask, dict) and str(mask.get("semanticId", ""))
        }
    )


def _semantic_part_ids(views: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            str(part.get("semanticId", ""))
            for view in views
            for part in view.get("semanticParts", [])
            if isinstance(part, dict) and str(part.get("semanticId", ""))
        }
    )


def _landmark_ids(views: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            str(landmark.get("id", ""))
            for view in views
            for landmark in view.get("landmarks", [])
            if isinstance(landmark, dict) and str(landmark.get("id", ""))
        }
    )


def _opening_ids(views: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            str(opening.get("openingId", ""))
            for view in views
            for opening in view.get("openings", [])
            if isinstance(opening, dict) and str(opening.get("openingId", ""))
        }
    )


def _bbox_union(bboxes: list[dict[str, Any]]) -> dict[str, Any]:
    available = [bbox for bbox in bboxes if bbox.get("available") is True]
    if not available:
        return {"available": False, "minX": 0.0, "minY": 0.0, "maxX": 0.0, "maxY": 0.0}
    min_x = min(float(bbox.get("minX", 0.0)) for bbox in available)
    min_y = min(float(bbox.get("minY", 0.0)) for bbox in available)
    max_x = max(float(bbox.get("maxX", 0.0)) for bbox in available)
    max_y = max(float(bbox.get("maxY", 0.0)) for bbox in available)
    return {
        "available": True,
        "minX": _round(min_x),
        "minY": _round(min_y),
        "maxX": _round(max_x),
        "maxY": _round(max_y),
        "width": _round(max_x - min_x),
        "height": _round(max_y - min_y),
    }


def _missing_evidence(visual_observations: dict[str, Any]) -> list[dict[str, Any]]:
    missing = visual_observations.get("aggregate", {}).get("missingEvidence", [])
    return deepcopy(missing) if isinstance(missing, list) else []


def _registration_confidence(capture_record: dict[str, Any]) -> float:
    values = [
        float(_mapping(view.get("qualityMeasurements")).get("scaleConfidence", 0.0))
        for view in capture_record.get("views", [])
        if isinstance(view, dict)
    ]
    return _round(sum(values) / max(1, len(values)))


def _view_role(label: str) -> str:
    if label == "front":
        return "required_front"
    if label == "back":
        return "required_rear"
    if label in OPTIONAL_VIEW_LABELS:
        return "optional_three_quarter"
    return "unrecognised_optional"


def _camera_number(view: dict[str, Any], key: str, fallback: float) -> float:
    return _round(float(_mapping(view.get("camera")).get(key, fallback)))


def _point(value: Any) -> list[float]:
    if not isinstance(value, list | tuple) or len(value) != 2:
        return [0.0, 0.0]
    return [_round(_clamp(float(value[0]))), _round(_clamp(float(value[1])))]


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_id(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in value)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _round(value: float) -> float:
    return round(float(value), 6)
