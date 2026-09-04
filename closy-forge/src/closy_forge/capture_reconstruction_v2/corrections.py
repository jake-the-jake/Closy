from __future__ import annotations

from copy import deepcopy
from typing import Any

from .common import canonical_digest

OPERATION_KINDS = (
    "capture_role_set",
    "crop_rotate_set",
    "garment_mask_add_remove",
    "semantic_mask_add_remove",
    "landmark_move_add_remove",
    "scale_target_set",
    "camera_hint_set",
    "frame_accept_reject",
    "print_logo_protection_set",
)


def apply_correction_journal(
    initial_state: dict[str, Any], operations: list[dict[str, Any]]
) -> dict[str, Any]:
    state = deepcopy(initial_state)
    history: list[dict[str, Any]] = []
    snapshots = [canonical_digest(state)]
    for sequence, operation in enumerate(operations, start=1):
        kind = str(operation.get("kind", ""))
        if kind not in OPERATION_KINDS:
            raise ValueError("correction_operation_unknown")
        before = canonical_digest(state)
        _apply(state, kind, operation)
        after = canonical_digest(state)
        if before == after:
            raise ValueError("correction_no_op_forbidden")
        invalidates = ["camera", "fit", "uv", "package", "evaluation"]
        history.append(
            {
                "sequence": sequence,
                "kind": kind,
                "beforeDigest": before,
                "afterDigest": after,
                "operatorIdentity": operation.get(
                    "operatorIdentity", "development-fixture-operator"
                ),
                "deterministicTimestamp": f"fixture-sequence-{sequence:03d}",
                "reason": operation.get("reason", "development_corruption_correction"),
                "reversible": True,
                "invalidates": invalidates,
            }
        )
        snapshots.append(after)
    replay = deepcopy(initial_state)
    for operation in operations:
        _apply(replay, str(operation["kind"]), operation)
    return {
        "schemaVersion": 2,
        "journalVersion": "closy.correction_journal.v2",
        "operationCount": len(history),
        "operations": history,
        "initialDigest": snapshots[0],
        "finalDigest": snapshots[-1],
        "replayDigest": canonical_digest(replay),
        "replayDeterministic": canonical_digest(replay) == snapshots[-1],
        "undoDigest": snapshots[0],
        "redoDigest": snapshots[-1],
        "allDownstreamInvalidated": all(
            set(row["invalidates"]) == {"camera", "fit", "uv", "package", "evaluation"}
            for row in history
        ),
        "finalState": state,
    }


def development_correction_fixture() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    initial: dict[str, Any] = {
        "captureRole": "unknown",
        "cropRotation": [0, 0, 256, 256, 0],
        "garmentMaskRevision": 0,
        "semanticMaskRevision": 0,
        "landmarks": {"shoulderL": [0.3, 0.3]},
        "scaleTarget": None,
        "cameraHint": None,
        "frameAccepted": True,
        "printProtection": [],
    }
    operations: list[dict[str, Any]] = [
        {"kind": "capture_role_set", "value": "worn"},
        {"kind": "crop_rotate_set", "value": [4, 5, 248, 250, 90]},
        {"kind": "garment_mask_add_remove", "value": 1},
        {"kind": "semantic_mask_add_remove", "value": 1},
        {
            "kind": "landmark_move_add_remove",
            "value": {"shoulderL": [0.28, 0.31], "neck": [0.5, 0.2]},
        },
        {"kind": "scale_target_set", "value": {"type": "checker", "meters": 0.2}},
        {"kind": "camera_hint_set", "value": {"yawRange": [-20, 20]}},
        {"kind": "frame_accept_reject", "value": False},
        {"kind": "print_logo_protection_set", "value": [[0.42, 0.31, 0.58, 0.49]]},
    ]
    return initial, operations


def _apply(state: dict[str, Any], kind: str, operation: dict[str, Any]) -> None:
    field_by_kind = {
        "capture_role_set": "captureRole",
        "crop_rotate_set": "cropRotation",
        "garment_mask_add_remove": "garmentMaskRevision",
        "semantic_mask_add_remove": "semanticMaskRevision",
        "landmark_move_add_remove": "landmarks",
        "scale_target_set": "scaleTarget",
        "camera_hint_set": "cameraHint",
        "frame_accept_reject": "frameAccepted",
        "print_logo_protection_set": "printProtection",
    }
    state[field_by_kind[kind]] = deepcopy(operation["value"])
