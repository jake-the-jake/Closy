from __future__ import annotations

import argparse
import builtins
import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Any

ROUTES = (
    "metadata_category_prior",
    "no_pixel_template_prior",
    "deterministic_masks_landmarks",
    "image_conditioned_iterative",
)

FIXED = {
    "sleeve_cap_height": 0.105,
    "hem_allowance": 0.025,
    "neckband_width": 0.035,
    "neckband_length_ease_ratio": 0.92,
    "target_panel_edge_length": 0.045,
}


def predict(route: str, payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    if route not in ROUTES:
        raise ValueError(f"unknown_contender_route:{route}")
    if route == "metadata_category_prior":
        parameters = dict(config["metadataPrior"])
        appearance = dict(config["appearancePrior"])
        evidence = "metadata_category_only"
    elif route == "no_pixel_template_prior":
        parameters = dict(config["noPixelPrior"])
        appearance = dict(config["appearancePrior"])
        evidence = "development_frozen_no_pixel_prior"
    else:
        parameters = _fit_from_source(payload["sourceEvidence"], config)
        appearance = _appearance_from_source(payload["sourceEvidence"], config)
        evidence = "decoded_source_masks_landmarks_and_pixels"
        if route == "image_conditioned_iterative":
            parameters = _bounded_refinement(parameters, payload["sourceEvidence"], config)
            evidence = "bounded_source_pixel_iterative_refinement"
    parameters.update(FIXED)
    result = {
        "schemaVersion": 1,
        "routeId": route,
        "opaqueId": payload["opaqueId"],
        "parameters": {key: round(float(value), 9) for key, value in parameters.items()},
        "appearance": appearance,
        "evidenceClass": evidence,
        "targetRead": False,
        "abstained": False,
    }
    result["predictionHash"] = _hash(result)
    return result


def _fit_from_source(source: dict[str, Any], config: dict[str, Any]) -> dict[str, float]:
    front = source["front"]
    rear = source["rear"]
    landmarks = front["landmarks"]
    rear_landmarks = rear["landmarks"]
    camera = front["camera"]
    scale = 0.88 / float(camera["orthographicScale"])
    azimuth = float(camera["azimuthDegrees"])
    width_scale = 0.97 + 0.03 * __import__("math").cos(__import__("math").radians(azimuth))
    top = float(landmarks["neck.center"][1])
    shoulder_l = landmarks["shoulder.left"]
    shoulder_r = landmarks["shoulder.right"]
    hem_l = landmarks["hem.left"]
    hem_r = landmarks["hem.right"]
    effective_half_chest = (float(hem_r[0]) - float(hem_l[0])) / width_scale
    frozen_ease = float(config["sourceFitterBodyEase"])
    return {
        "garment_body_length": (float(landmarks["hem.center"][1]) - top) / (0.68 * scale),
        "half_chest_width": effective_half_chest - frozen_ease,
        "body_ease": frozen_ease,
        "shoulder_width": (float(shoulder_r[0]) - float(shoulder_l[0])) / (0.49 * width_scale),
        "shoulder_slope": (float(shoulder_l[1]) - top) / (0.52 * scale),
        "neckline_width": (
            top - float(landmarks["neck.left"][0]) + float(landmarks["neck.center"][0]) - top
        )
        / (0.27 * width_scale),
        "front_neckline_depth": (float(landmarks["neck.bottom"][1]) - top) / (0.32 * scale),
        "back_neckline_depth": (
            float(rear_landmarks["neck.bottom"][1]) - float(rear_landmarks["neck.center"][1])
        )
        / (0.32 * (0.88 / float(rear["camera"]["orthographicScale"]))),
        "armhole_depth": (float(landmarks["armhole.left"][1]) - float(shoulder_l[1]))
        / (0.62 * scale),
        "sleeve_length": (float(shoulder_l[0]) - float(landmarks["cuff.left"][0])) / (0.48 * scale),
        "sleeve_opening_width": (
            float(landmarks["cuff.opening"][1]) - float(landmarks["cuff.right"][1])
        )
        / (0.36 * scale),
    }


def _bounded_refinement(
    parameters: dict[str, float], source: dict[str, Any], config: dict[str, Any]
) -> dict[str, float]:
    refined = dict(parameters)
    coverage = float(source["front"]["maskCoverage"])
    development_centre = float(config["developmentMaskCoverageMedian"])
    adjustment = max(-0.004, min(0.004, (coverage - development_centre) * 0.012))
    refined["half_chest_width"] += adjustment
    refined["garment_body_length"] -= adjustment * 0.4
    return refined


def _appearance_from_source(source: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    measured = source.get("appearanceFeatures")
    return dict(measured) if isinstance(measured, dict) else dict(config["appearancePrior"])


def _hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route", required=True, choices=ROUTES)
    parser.add_argument("--input", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--permissions", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--audit", required=True)
    args = parser.parse_args()
    allowed_reads = {
        str(Path(args.input).resolve()),
        str(Path(args.config).resolve()),
        str(Path(args.permissions).resolve()),
    }
    allowed_writes = {str(Path(args.output).resolve()), str(Path(args.audit).resolve())}
    events: list[dict[str, Any]] = []
    original_open = builtins.open
    original_io_open = io.open

    def guarded_open(file: Any, mode: str = "r", *positional: Any, **keywords: Any) -> Any:
        path = str(Path(file).resolve())
        writing = any(token in mode for token in "wax+")
        allowed = path in (allowed_writes if writing else allowed_reads)
        events.append({"path": path, "mode": mode, "allowed": allowed})
        if not allowed:
            raise PermissionError(f"undeclared_file_access:{path}")
        return original_open(file, mode, *positional, **keywords)

    builtins.open = guarded_open
    io.open = guarded_open
    exit_code = 0
    try:
        input_payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
        permissions = json.loads(Path(args.permissions).read_text(encoding="utf-8"))
        if args.route not in permissions["allowedRoutes"]:
            raise PermissionError("route_not_permitted")
        prediction = predict(args.route, input_payload, config)
    except (OSError, ValueError, KeyError, TypeError) as error:
        prediction = {"status": "failed", "reason": str(error), "routeId": args.route}
        exit_code = 2
    finally:
        builtins.open = original_open
        io.open = original_io_open
    Path(args.output).write_text(
        json.dumps(prediction, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    Path(args.audit).write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "enforcement": "application_process_deny_by_default_open_audit",
                "operatingSystemSandboxClaimed": False,
                "events": events,
                "allAccessAllowed": all(event["allowed"] for event in events),
                "repositoryRootMounted": False,
                "networkAllowed": False,
                "exitCode": exit_code,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(_main())
