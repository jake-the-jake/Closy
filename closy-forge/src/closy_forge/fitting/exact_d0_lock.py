from __future__ import annotations

import json
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import Any

from closy_forge.package_io.hashing import sha256_file

EXACT_D0_EVALUATION_LOCK_PATH = Path("fixtures/d0_exact_fitting_v2/evaluation_lock.json")
EXACT_D0_EVALUATION_LOCK_SHA256 = "4d3fe057a08395a26cb4f4185c0940d0bba38f0ac66bc68e5ad47b01296f5d98"


def load_exact_d0_evaluation_lock(root: Path) -> dict[str, Any]:
    path = root / EXACT_D0_EVALUATION_LOCK_PATH
    if sha256_file(path) != EXACT_D0_EVALUATION_LOCK_SHA256:
        raise ValueError("exact_d0_evaluation_lock_hash_mismatch")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("exact_d0_evaluation_lock_invalid")
    _validate_lock(root, payload)
    return payload


def _validate_lock(root: Path, lock: Mapping[str, Any]) -> None:
    if lock.get("lockId") != "closy.d0_exact_fitting_pbr_evaluation_lock.v2":
        raise ValueError("exact_d0_evaluation_lock_id_invalid")
    if (
        _mapping(lock.get("calibrationPolicy")).get("selectedIdentityUsedForCalibration")
        is not False
    ):
        raise ValueError("exact_d0_selected_identity_used_for_calibration")

    templates = lock.get("templateSet")
    if not isinstance(templates, list) or len(templates) < 3:
        raise ValueError("exact_d0_template_set_too_small")
    template_ids = [str(_mapping(item).get("templateId", "")) for item in templates]
    if len(set(template_ids)) != len(template_ids) or any(not item for item in template_ids):
        raise ValueError("exact_d0_template_ids_invalid")

    bounds = _mapping(lock.get("parameterBounds"))
    for template in templates:
        prior = _mapping(_mapping(template).get("prior"))
        if set(prior) != set(bounds):
            raise ValueError("exact_d0_template_parameter_set_mismatch")
        for parameter, value in prior.items():
            interval = bounds.get(parameter)
            if not isinstance(interval, list) or len(interval) != 2:
                raise ValueError("exact_d0_parameter_bounds_invalid")
            if not float(interval[0]) <= float(value) <= float(interval[1]):
                raise ValueError(f"exact_d0_template_parameter_out_of_bounds:{parameter}")

    contenders = lock.get("contenders")
    if not isinstance(contenders, list):
        raise ValueError("exact_d0_contenders_invalid")
    contender_map = {
        str(_mapping(item).get("contenderId", "")): _mapping(item) for item in contenders
    }
    required = {
        "metadata_category_prior",
        "no_pixel_template",
        "deterministic_mask_landmark",
        "image_conditioned",
    }
    if set(contender_map) != required:
        raise ValueError("exact_d0_contender_set_mismatch")
    for baseline in ("metadata_category_prior", "no_pixel_template"):
        if contender_map[baseline].get("rawPixels") is not False:
            raise ValueError("exact_d0_baseline_raw_pixel_access")
        if contender_map[baseline].get("derivedEvidence") is not False:
            raise ValueError("exact_d0_baseline_derived_access")
    if any(item.get("hiddenFixtureParameters") is not False for item in contender_map.values()):
        raise ValueError("exact_d0_hidden_parameters_permitted")

    cameras = lock.get("sourceCameras")
    if not isinstance(cameras, list):
        raise ValueError("exact_d0_cameras_invalid")
    roles = {str(_mapping(camera).get("role", "")) for camera in cameras}
    if roles != {
        "fit_front",
        "fit_rear",
        "evaluator_only_after_prediction_and_atlas_freeze",
    }:
        raise ValueError("exact_d0_camera_roles_invalid")

    held_out = _mapping(lock.get("heldOutPolicy"))
    if held_out.get("rearCalledHeldOut") is not False:
        raise ValueError("exact_d0_rear_mislabeled_held_out")
    if held_out.get("evaluatorOnlyViewMountedBeforeFreeze") is not False:
        raise ValueError("exact_d0_evaluator_view_mounted_before_freeze")

    code_identities = _mapping(lock.get("codeIdentities"))
    for record in code_identities.values():
        if not isinstance(record, Mapping):
            continue
        path = record.get("path")
        digest = record.get("sha256")
        if (
            isinstance(path, str)
            and isinstance(digest, str)
            and not _matches_locked_source_hash(root / path, digest)
        ):
            raise ValueError(f"exact_d0_locked_code_hash_mismatch:{path}")


def _matches_locked_source_hash(path: Path, expected: str) -> bool:
    raw = path.read_bytes()
    if sha256(raw).hexdigest() == expected:
        return True
    # The frozen Windows lock predates the repository-wide LF checkout policy. Accept only the
    # byte-equivalent CRLF form; arbitrary source changes still fail closed.
    canonical_crlf = raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return sha256(canonical_crlf).hexdigest() == expected


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
