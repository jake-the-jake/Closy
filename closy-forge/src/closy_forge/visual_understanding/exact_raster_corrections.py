from __future__ import annotations

from copy import deepcopy
from typing import Any

from closy_forge.capture.exact_raster_identity import build_exact_capture_record
from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.visual_understanding.corrections import (
    CorrectionReplayError,
    apply_correction_operations,
    build_applied_correction_record,
    build_empty_correction_record,
    hash_correction_record,
)
from closy_forge.visual_understanding.multiview_fusion import build_multiview_fusion_record

EXACT_CORRECTION_VERSION = "closy.correction_record.exact_raster_d0_v2"


def build_exact_raster_correction_evidence(
    lineage_result: dict[str, Any],
) -> dict[str, Any]:
    observations = lineage_result["observations"]
    before_hash = str(observations["integrity"]["visualRecordHash"])
    approval = build_empty_correction_record(observations)
    approval["correctionRecordId"] = "correction.exact_raster_d0_approval_v2"
    approval["recordVersion"] = EXACT_CORRECTION_VERSION
    approval["state"] = "project_authored_no_op_approval"
    approval["authorClassification"] = "project_authored_d0_correction_evidence"
    approval["interactiveUserActionClaimed"] = False
    approval["integrity"]["correctionRecordHash"] = hash_correction_record(approval)

    operation = {
        "operationId": "op.exact.0001.snap.front_hem_center",
        "operation": "landmark_move",
        "viewId": "view.front",
        "landmarkId": "landmark.hem.center",
        "position2d": [0.5, 0.78125],
        "confidence": 0.94,
        "boundedDelta": {
            "maximumNormalizedDistance": 0.01,
            "observedNormalizedDistance": 0.00375,
        },
        "affectedSemanticEntities": ["opening.hem", "landmark.hem.center"],
        "expectedVisualRecordHash": before_hash,
    }
    selected = build_applied_correction_record(observations, [operation])
    selected["correctionRecordId"] = "correction.exact_raster_d0_selected_v2"
    selected["recordVersion"] = EXACT_CORRECTION_VERSION
    selected["authorClassification"] = "project_authored_d0_correction_evidence"
    selected["interactiveUserActionClaimed"] = False
    selected["selectionStatus"] = "selected_before_fit"
    selected["integrity"]["correctionRecordHash"] = hash_correction_record(selected)
    corrected = apply_correction_operations(observations, selected["operations"])
    capture = build_exact_capture_record(lineage_result)
    approval_fusion = build_multiview_fusion_record(capture, observations, approval)
    fusion = build_multiview_fusion_record(capture, observations, selected)
    approval_cache_key = _downstream_cache_key(
        source_hash=str(lineage_result["lineage"]["integrity"]["lineageHash"]),
        original_visual_hash=before_hash,
        correction_hash=str(approval["integrity"]["correctionRecordHash"]),
        corrected_visual_hash=before_hash,
        fusion_hash=str(approval_fusion["integrity"]["multiviewFusionRecordHash"]),
    )
    cache_key = _downstream_cache_key(
        source_hash=str(lineage_result["lineage"]["integrity"]["lineageHash"]),
        original_visual_hash=before_hash,
        correction_hash=str(selected["integrity"]["correctionRecordHash"]),
        corrected_visual_hash=str(corrected["integrity"]["visualRecordHash"]),
        fusion_hash=str(fusion["integrity"]["multiviewFusionRecordHash"]),
    )
    stale = _stale_rejection_control(observations)
    evidence = {
        "schemaVersion": 1,
        "evidenceVersion": "closy.d0_exact_raster_correction_evidence.v2",
        "classification": "project_authored_public_synthetic_d0",
        "originalObservation": {
            "visualUnderstandingId": observations["visualUnderstandingId"],
            "visualRecordHash": before_hash,
        },
        "approvalRecord": approval,
        "selectedCorrectionRecord": selected,
        "correctedObservation": corrected,
        "multiviewFusion": fusion,
        "staleCorrectionControl": stale,
        "selectionContract": {
            "selectedBeforeFit": True,
            "selectedCorrectionRecordId": selected["correctionRecordId"],
            "selectedCorrectionRecordHash": selected["integrity"]["correctionRecordHash"],
            "requiredCorrectedVisualRecordHash": corrected["integrity"]["visualRecordHash"],
            "requiredMultiviewFusionRecordHash": fusion["integrity"]["multiviewFusionRecordHash"],
            "requiredDownstreamCacheKey": cache_key,
            "approvalDownstreamCacheKey": approval_cache_key,
            "unitCFitMustConsumeAllRequiredIdentities": True,
        },
        "claims": {
            "correctionChangesVisualHash": (
                corrected["integrity"]["visualRecordHash"] != before_hash
            ),
            "correctionChangesDownstreamCacheKey": cache_key != approval_cache_key,
            "staleCorrectionRejected": stale["rejected"],
            "interactiveCorrectionUiBuilt": False,
            "userPerformedCorrection": False,
        },
        "integrity": {"correctionEvidenceHash": ""},
    }
    return finalize_exact_raster_correction_evidence(evidence)


def finalize_exact_raster_correction_evidence(value: dict[str, Any]) -> dict[str, Any]:
    finalized = deepcopy(value)
    finalized["integrity"]["correctionEvidenceHash"] = _record_hash(
        finalized, "correctionEvidenceHash"
    )
    return finalized


def _stale_rejection_control(observations: dict[str, Any]) -> dict[str, Any]:
    operation = {
        "operationId": "op.exact.stale.control",
        "operation": "landmark_move",
        "viewId": "view.front",
        "landmarkId": "landmark.hem.center",
        "position2d": [0.5, 0.78],
        "expectedVisualRecordHash": "0" * 64,
    }
    try:
        build_applied_correction_record(observations, [operation])
    except CorrectionReplayError as error:
        return {
            "rejected": True,
            "reasonCode": error.code,
            "rawPixelsOrPathsInError": False,
        }
    return {"rejected": False, "reasonCode": "unexpected_acceptance"}


def _downstream_cache_key(
    *,
    source_hash: str,
    original_visual_hash: str,
    correction_hash: str,
    corrected_visual_hash: str,
    fusion_hash: str,
) -> str:
    return sha256_bytes(
        b"CLOSY_EXACT_RASTER_D0_CORRECTED_FIT_CACHE_V2"
        + canonical_dumps(
            {
                "sourceHash": source_hash,
                "originalVisualHash": original_visual_hash,
                "correctionHash": correction_hash,
                "correctedVisualHash": corrected_visual_hash,
                "fusionHash": fusion_hash,
            }
        ).encode("utf-8")
    )


def _record_hash(value: dict[str, Any], key: str) -> str:
    payload = deepcopy(value)
    payload["integrity"][key] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
