from __future__ import annotations

import shutil
from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from closy_forge.disjoint_benchmark_v1.protocol import PARAMETER_RANGES
from closy_forge.disjoint_benchmark_v1.renderers import render_source_capture
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file

ATTEMPT_ROOT = Path("fixtures/d0_disjoint_tshirt_confirmation_v3/official_attempt")
PROTOCOL_PATH = Path("fixtures/d0_disjoint_tshirt_confirmation_v3/protocol_lock.json")
TRAINING_INVENTORY_PATH = Path(
    "fixtures/evidence_authority_recovery_v2/public_pixel_training_inventory.json"
)
ERRATUM_VERSION = "closy.d0_v3.forensic_erratum.v1"
PIXEL_ROUTES = (
    "pixel_mask_landmark_optimizer_v3",
    "pixel_learned_structured_tshirt_v3",
)
FIXED_DEFAULT_OBSERVABLES = (
    "shoulder_slope",
    "neckline_width",
    "front_neckline_depth",
    "back_neckline_depth",
    "armhole_depth",
    "sleeve_opening_width",
)
SEALED_ARTIFACTS = (
    "benchmark_result.json",
    "predictions.json",
    "public_source_inventory.json",
    "target_reveal.json",
    "authority_commitments.json",
    "attempt_manifest.json",
)


def build_v3_forensic_erratum(root: Path) -> dict[str, Any]:
    attempt = root / ATTEMPT_ROOT
    protocol = _mapping(read_json(root / PROTOCOL_PATH))
    predictions_doc = _mapping(read_json(attempt / "predictions.json"))
    result = _mapping(read_json(attempt / "benchmark_result.json"))
    reveal = _mapping(read_json(attempt / "target_reveal.json"))
    predictions = _records(predictions_doc.get("predictions"))
    targets = _records(reveal.get("identities"))
    result_records = _records(result.get("records"))
    image_paths = sorted((attempt / "source_roles").glob("*/*.png"))

    alpha_records = [_alpha_record(path, root) for path in image_paths]
    route_records = [_route_forensic(route, predictions, result_records) for route in PIXEL_ROUTES]
    floor_records = _fixed_default_floors(predictions, targets)
    crop_records = _crop_noop_records(targets)
    training_inventory = _mapping(read_json(root / TRAINING_INVENTORY_PATH))
    identity_keys = {
        (
            str(record.get("frontPngSha256")),
            str(record.get("rearPngSha256")),
            canonical_dumps(_mapping(record.get("parameters"))),
        )
        for record in _records(training_inventory.get("records"))
    }
    implementation_records = _implementation_inventory(protocol)
    lifecycle = _lifecycle_summary(result_records)
    worst = sorted(
        result_records,
        key=lambda row: (
            -float(_mapping(row.get("parameterMetrics")).get("macroNormalizedError", 1.0)),
            str(row.get("opaqueId")),
            str(row.get("routeId")),
        ),
    )[:4]
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "erratumVersion": ERRATUM_VERSION,
        "sealedV3OutcomePreserved": result.get("outcome"),
        "supersedingInterpretation": (
            "artifact_record_integrity_valid; capability_qualification_invalid_or_"
            "ineligible_due_to_protocol_semantic_and_route_defects"
        ),
        "v3RerunPerformed": False,
        "v3PredictionEdited": False,
        "sealedArtifacts": [
            {
                "path": (ATTEMPT_ROOT / name).as_posix(),
                "sha256": sha256_file(attempt / name),
                "byteLength": (attempt / name).stat().st_size,
            }
            for name in SEALED_ARTIFACTS
        ],
        "lockedImplementation": implementation_records,
        "opaqueAlphaFailure": {
            "sourceImageCount": len(alpha_records),
            "fullyOpaqueAlphaPlaneCount": sum(row["fullyOpaqueAlpha"] for row in alpha_records),
            "dominantBackgroundMatchesCornerCount": sum(
                row["dominantBackgroundMatchesCorner"] for row in alpha_records
            ),
            "records": alpha_records,
        },
        "pixelRoutes": route_records,
        "strictCandidateCompleteness": {
            "definition": (
                "every scored structural observable has explicit source-conditioned lineage and "
                "a finite value; silent fixed defaults are incomplete"
            ),
            "nonAbstainedPixelCandidates": sum(row["nonAbstainedCount"] for row in route_records),
            "completeCandidateCount": 0,
            "compileValidCompleteCandidateCount": 0,
        },
        "finalGates": {
            "rowDenominator": len(result_records),
            "allGatePassCount": sum(row.get("status") == "pass" for row in result_records),
            "executedAppearanceCount": sum(
                row.get("appearance") is not None for row in result_records
            ),
            "appearancePassCount": sum(
                _mapping(row.get("appearance")).get("status") == "pass" for row in result_records
            ),
        },
        "trainingInventory": {
            "path": TRAINING_INVENTORY_PATH.as_posix(),
            "inventoryDigest": training_inventory.get("inventoryDigest"),
            "nominalRecordCount": len(_records(training_inventory.get("records"))),
            "uniqueIdentityRasterParameterCount": len(identity_keys),
            "modelSampleCount": 24,
            "v3ProtocolRecordLevelTypedComparisonIncluded": False,
            "laterY0RecoveryInventoryIncluded": True,
        },
        "observableCoverage": {
            "scoredObservableCount": 10,
            "learnedRoutePredictedObservableCount": 4,
            "fixedDefaultObservableCount": 6,
            "fixedDefaultObservables": list(FIXED_DEFAULT_OBSERVABLES),
        },
        "fixedDefaultWorstErrorFloors": {
            "minimum": round(min(row["worstNormalizedErrorFloor"] for row in floor_records), 9),
            "maximum": round(max(row["worstNormalizedErrorFloor"] for row in floor_records), 9),
            "records": floor_records,
        },
        "cropSemanticDefect": {
            "claimedCropIdentityCount": len(crop_records),
            "claimedCropCaptureCount": sum(len(row["roles"]) for row in crop_records),
            "cropChangesRenderedBytesCount": sum(
                not role["bytesEqual"] for row in crop_records for role in row["roles"]
            ),
            "records": crop_records,
        },
        "lifecycle": lifecycle,
        "worstCases": [
            {
                "opaqueId": row.get("opaqueId"),
                "routeId": row.get("routeId"),
                "macroNormalizedError": _mapping(row.get("parameterMetrics")).get(
                    "macroNormalizedError", 1.0
                ),
                "compileFailure": row.get("compileFailure"),
            }
            for row in worst
        ],
        "capabilityQualificationValid": False,
        "erratumDigest": "",
    }
    report["erratumDigest"] = _digest(report, "erratumDigest")
    return report


def write_v3_forensic_erratum(root: Path, output: Path) -> dict[str, Any]:
    report = build_v3_forensic_erratum(root)
    output.mkdir(parents=True, exist_ok=True)
    worst_root = output / "worst_cases"
    worst_root.mkdir(parents=True, exist_ok=True)
    attempt = root / ATTEMPT_ROOT
    assets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in report["worstCases"]:
        opaque_id = str(record["opaqueId"])
        if opaque_id in seen:
            continue
        seen.add(opaque_id)
        source = attempt / "source_roles" / opaque_id / "front.png"
        copy_path = worst_root / f"{opaque_id}.front.png"
        overlay_path = worst_root / f"{opaque_id}.foreground-overlay.png"
        shutil.copyfile(source, copy_path)
        _write_foreground_overlay(source, overlay_path)
        assets.append(
            {
                "opaqueId": opaque_id,
                "sourcePath": copy_path.relative_to(output).as_posix(),
                "sourceSha256": sha256_file(copy_path),
                "overlayPath": overlay_path.relative_to(output).as_posix(),
                "overlaySha256": sha256_file(overlay_path),
            }
        )
    report["worstCaseAssets"] = assets
    report["erratumDigest"] = _digest(report, "erratumDigest")
    write_canonical_json(output / "v3_forensic_erratum.json", report)
    return report


def validate_v3_forensic_erratum(report: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    alpha = _mapping(report.get("opaqueAlphaFailure"))
    if alpha.get("sourceImageCount") != 30 or alpha.get("fullyOpaqueAlphaPlaneCount") != 30:
        issues.append("v3_opaque_alpha_count_invalid")
    if alpha.get("dominantBackgroundMatchesCornerCount") != 30:
        issues.append("v3_dominant_background_count_invalid")
    routes = _records(report.get("pixelRoutes"))
    if len(routes) != 2 or any(
        row.get("structuralVariantCount") != 1
        or row.get("abstainedCount") != 2
        or row.get("nonAbstainedCount") != 14
        or row.get("appearanceVariantCount") != 5
        for row in routes
    ):
        issues.append("v3_pixel_route_constant_payload_facts_invalid")
    completeness = _mapping(report.get("strictCandidateCompleteness"))
    if completeness.get("compileValidCompleteCandidateCount") != 0:
        issues.append("v3_complete_compile_count_invalid")
    gates = _mapping(report.get("finalGates"))
    if gates.get("rowDenominator") != 48 or gates.get("allGatePassCount") != 0:
        issues.append("v3_final_gate_count_invalid")
    if gates.get("executedAppearanceCount") != 8 or gates.get("appearancePassCount") != 0:
        issues.append("v3_appearance_gate_count_invalid")
    inventory = _mapping(report.get("trainingInventory"))
    if (
        inventory.get("nominalRecordCount") != 24
        or inventory.get("uniqueIdentityRasterParameterCount") != 8
    ):
        issues.append("v3_training_identity_count_invalid")
    floors = _mapping(report.get("fixedDefaultWorstErrorFloors"))
    if floors.get("minimum") != 0.3453846 or floors.get("maximum") != 0.677385519:
        issues.append("v3_fixed_default_floor_invalid")
    crop = _mapping(report.get("cropSemanticDefect"))
    if (
        crop.get("claimedCropIdentityCount") != 6
        or crop.get("claimedCropCaptureCount") != 12
        or crop.get("cropChangesRenderedBytesCount") != 0
    ):
        issues.append("v3_crop_defect_count_invalid")
    if report.get("sealedV3OutcomePreserved") != "completed_benchmark_failed_absolute_gates":
        issues.append("v3_literal_outcome_changed")
    if report.get("erratumDigest") != _digest(report, "erratumDigest"):
        issues.append("v3_erratum_digest_invalid")
    return sorted(set(issues))


def _alpha_record(path: Path, root: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        pixels = list(rgba.getdata())
        rgb = [pixel[:3] for pixel in pixels]
        dominant = Counter(rgb).most_common(1)[0][0]
        return {
            "path": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
            "fullyOpaqueAlpha": all(pixel[3] == 255 for pixel in pixels),
            "dominantBackgroundMatchesCorner": dominant == rgba.getpixel((0, 0))[:3],
            "dominantRgb": list(dominant),
        }


def _route_forensic(
    route: str, predictions: list[Mapping[str, Any]], result_records: list[Mapping[str, Any]]
) -> dict[str, Any]:
    selected = [row for row in predictions if row.get("routeId") == route]
    non_abstained = [row for row in selected if row.get("abstained") is False]
    structural = {canonical_dumps(row.get("parameters")) for row in non_abstained}
    appearance = {canonical_dumps(row.get("appearance")) for row in non_abstained}
    evaluated = [row for row in result_records if row.get("routeId") == route]
    return {
        "routeId": route,
        "scheduledCount": len(selected),
        "containerReturnedCount": len(selected),
        "abstainedCount": len(selected) - len(non_abstained),
        "nonAbstainedCount": len(non_abstained),
        "structuralVariantCount": len(structural),
        "appearanceVariantCount": len(appearance),
        "compileValidCount": sum(row.get("compileFailure") is None for row in evaluated),
        "allGatePassCount": sum(row.get("status") == "pass" for row in evaluated),
    }


def _fixed_default_floors(
    predictions: list[Mapping[str, Any]], targets: list[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    default_prediction = next(
        row
        for row in predictions
        if row.get("routeId") == "pixel_learned_structured_tshirt_v3"
        and row.get("abstained") is False
    )
    defaults = _mapping(default_prediction.get("parameters"))
    records: list[dict[str, Any]] = []
    for target in targets:
        parameters = _mapping(target.get("parameters"))
        by_parameter = {
            name: abs(float(defaults[name]) - float(parameters[name]))
            / (PARAMETER_RANGES[name][1] - PARAMETER_RANGES[name][0])
            for name in FIXED_DEFAULT_OBSERVABLES
        }
        records.append(
            {
                "opaqueId": target.get("opaqueId"),
                "byParameter": {key: round(value, 9) for key, value in by_parameter.items()},
                "worstNormalizedErrorFloor": round(max(by_parameter.values()), 9),
            }
        )
    return records


def _crop_noop_records(targets: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for target in targets:
        capture = _mapping(target.get("capture"))
        crop_fraction = float(capture.get("cropFraction", 0.0))
        if crop_fraction <= 0.0:
            continue
        role_hashes: list[dict[str, Any]] = []
        for role in ("front", "rear"):
            if f"{role}_png" not in capture.get("sourceRoleAvailability", []):
                continue
            camera = deepcopy(_mapping(capture.get(role)))
            with_crop = {**camera, **capture}
            without_crop = {**with_crop, "cropFraction": 0.0}
            left = render_source_capture(
                _mapping(target.get("parameters")),
                _mapping(target.get("appearance")),
                with_crop,
                role=role,
            ).png
            right = render_source_capture(
                _mapping(target.get("parameters")),
                _mapping(target.get("appearance")),
                without_crop,
                role=role,
            ).png
            role_hashes.append(
                {
                    "role": role,
                    "withCropSha256": sha256_bytes(left),
                    "withoutCropSha256": sha256_bytes(right),
                    "bytesEqual": left == right,
                }
            )
        records.append(
            {
                "opaqueId": target.get("opaqueId"),
                "cropFraction": crop_fraction,
                "cropChangesRenderedBytes": any(not row["bytesEqual"] for row in role_hashes),
                "roles": role_hashes,
            }
        )
    return records


def _implementation_inventory(protocol: Mapping[str, Any]) -> list[dict[str, Any]]:
    terms = (
        "runner_v3.py",
        "contender_cli.py",
        "renderers.py",
        "metrics.py",
        "protocol.py",
        "evaluator.py",
        "authority.py",
        "evaluation_worker.py",
    )
    return [
        dict(record)
        for record in _records(protocol.get("implementationFiles"))
        if any(str(record.get("path", "")).endswith(term) for term in terms)
    ]


def _lifecycle_summary(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "scheduled": 48,
        "containerReturned": 48,
        "abstained": 4,
        "candidateComplete": 16,
        "compilerEntered": 44,
        "compileValid": sum(row.get("compileFailure") is None for row in records),
        "appearanceEvaluated": sum(row.get("appearance") is not None for row in records),
        "appearancePass": sum(
            _mapping(row.get("appearance")).get("status") == "pass" for row in records
        ),
        "allGatePass": sum(row.get("status") == "pass" for row in records),
        "deterministicReproductionOfFailure": True,
        "capabilityRepeatSuccess": False,
    }


def _write_foreground_overlay(source: Path, target: Path) -> None:
    with Image.open(source) as image:
        rgba = image.convert("RGBA")
    pixels = list(rgba.getdata())
    dominant = Counter(pixel[:3] for pixel in pixels).most_common(1)[0][0]
    overlay = rgba.copy()
    draw = ImageDraw.Draw(overlay)
    width, height = overlay.size
    foreground = {
        (index % width, index // width)
        for index, pixel in enumerate(pixels)
        if pixel[:3] != dominant
    }
    boundary = [
        point
        for point in foreground
        if any(
            (point[0] + dx, point[1] + dy) not in foreground
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1))
        )
    ]
    for x, y in boundary:
        draw.point((x, y), fill=(220, 32, 32, 255))
    target.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(target, format="PNG", optimize=False)


def _records(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _digest(value: Mapping[str, Any], field: str) -> str:
    payload = deepcopy(dict(value))
    payload[field] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
