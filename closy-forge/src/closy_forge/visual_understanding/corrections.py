from __future__ import annotations

from copy import deepcopy
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

CORRECTION_RECORD_VERSION = "closy.correction_record.empty_v1"


def build_empty_correction_record(visual_observations: dict[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schemaVersion": 1,
        "correctionRecordId": "correction.synthetic_tshirt_empty_v1",
        "recordVersion": CORRECTION_RECORD_VERSION,
        "visualUnderstandingId": visual_observations["visualUnderstandingId"],
        "visualRecordHash": visual_observations["integrity"]["visualRecordHash"],
        "state": "empty_editable_baseline",
        "editable": True,
        "privacy": {
            "containsUserImagery": False,
            "containsPersonalBodyData": False,
            "allowExternalApis": False,
            "allowTrainingUse": False,
        },
        "allowedOperations": [
            "mask_polygon_edit",
            "landmark_move",
            "semantic_label_override",
            "confidence_override",
        ],
        "operations": [],
        "integrity": {"correctionRecordHash": ""},
    }
    record["integrity"]["correctionRecordHash"] = hash_correction_record(record)
    return record


def hash_correction_record(record: dict[str, Any]) -> str:
    payload = deepcopy(record)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["correctionRecordHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
