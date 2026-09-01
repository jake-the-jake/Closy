from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path
from statistics import median
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.raster import decode_png_rgba

from .contender_cli import ROUTES
from .corpus import RealizedIdentity, default_prior, realize_identities
from .isolation import execute_isolated_contender
from .metrics import mode_colour, observable_parameter_errors
from .protocol import FIXTURE_ROOT, OBSERVABLE_PARAMETERS
from .renderers import SourceCapture, render_source_capture, source_features

DEVELOPMENT_SEED = "c10sy-d0-disjoint-development-v1-public-seed-2026"


def generate_development_lock(
    root: Path,
    *,
    source_anchor_sha: str,
    output: Path | None = None,
) -> dict[str, Any]:
    target = output or root / FIXTURE_ROOT
    prior = default_prior()
    references = [prior, _boxy_reference(prior), _long_reference(prior)]
    identities, transcript = realize_identities(
        seed_hex=DEVELOPMENT_SEED,
        count=8,
        role="development",
        minimum_prior_distance=0.15,
        references=references,
        maximum_attempts=4096,
    )
    config = _development_config(identities)
    executable = root / "src/closy_forge/disjoint_benchmark_v1/contender_cli.py"
    results: list[dict[str, Any]] = []
    source_records: list[dict[str, Any]] = []
    for identity in identities:
        source = build_source_evidence(identity)
        source_records.append(_persist_development_identity(target, identity, source))
        for route in ROUTES:
            payload = contestant_input(identity.opaque_id, source, route)
            prediction, isolation = execute_isolated_contender(
                executable=executable,
                route=route,
                input_payload=payload,
                config=config,
            )
            errors = observable_parameter_errors(prediction["parameters"], identity.parameters)
            results.append(
                {
                    "opaqueId": identity.opaque_id,
                    "routeId": route,
                    "predictionHash": prediction["predictionHash"],
                    "metrics": errors,
                    "isolation": isolation,
                }
            )
    route_summaries = _route_summaries(results)
    primary = min(
        (item for item in route_summaries if item["routeId"] in ROUTES[2:]),
        key=lambda item: (item["medianMacroNormalizedError"], item["routeId"]),
    )["routeId"]
    lock: dict[str, Any] = {
        "schemaVersion": 1,
        "lockVersion": "closy.d0_disjoint.development_lock.v1",
        "sourceAnchorSha": source_anchor_sha,
        "developmentSeed": DEVELOPMENT_SEED,
        "developmentIdentityCount": 8,
        "evaluatorIdentityCount": 16,
        "developmentIdentities": source_records,
        "developmentTranscriptHash": _hash(transcript),
        "developmentResults": results,
        "routeSummaries": route_summaries,
        "contenderConfiguration": config,
        "primaryGateRoute": primary,
        "primarySelectionRule": (
            "minimum_development_median_macro_observable_error_then_lexical_route_id_"
            "among_source_conditioned_routes"
        ),
        "fullCompileRouteIds": ["no_pixel_template_prior", primary, "image_conditioned_iterative"],
        "appearanceRouteIds": ["no_pixel_template_prior", primary, "image_conditioned_iterative"],
        "appearanceEvaluatorOrdinals": list(range(8)),
        "appearanceExpectedStrata": [
            "logo_absent",
            "logo_present",
            "controlled_capture",
            "shape_extreme",
        ]
        * 2,
        "normalization": {
            "observableParameters": [
                "garment_body_length",
                "effective_half_chest_width",
                "shoulder_width",
                "shoulder_slope",
                "neckline_width",
                "front_neckline_depth",
                "back_neckline_depth",
                "armhole_depth",
                "sleeve_length",
                "sleeve_opening_width",
            ],
            "individualHalfChestAndEaseIdentifiable": False,
            "effectiveHalfChestDefinition": "half_chest_width_plus_body_ease",
            "unidentifiableControlsHeldFixed": [
                "sleeve_cap_height",
                "hem_allowance",
                "neckband_width",
                "neckband_length_ease_ratio",
                "target_panel_edge_length",
            ],
        },
        "absoluteThresholds": _absolute_thresholds(),
        "promotionThresholds": {
            "primaryVersusNoPixelParameterRelativeImprovementMinimum": 0.10,
            "primaryVersusNoPixelSilhouetteAbsoluteImprovementMinimum": 0.01,
            "learnedWinnerParameterRelativeImprovementMinimum": 0.20,
            "learnedWinnerSilhouetteAbsoluteImprovementMinimum": 0.02,
            "bootstrapLower95MustClearZero": True,
            "bootstrapResamples": 10000,
            "bootstrapSeed": 4107301,
            "tiesSelectSimplerLowerEvidenceRoute": True,
        },
        "failurePenalty": {"macroNormalizedError": 1.0, "silhouetteIoU": 0.0},
        "budgets": {
            "maximumFullCompiles": 64,
            "maximumAppearanceEvaluations": 32,
            "primaryRepeatFullCompiles": 16,
            "primaryRepeatAppearanceEvaluations": 8,
            "repeatReserveReassignable": False,
        },
        "phase9Route": {
            "eligible": False,
            "reason": "persisted_phase9_model_does_not_emit_exact_tshirt_canonical_contract",
            "trainingOrCalibrationOnEvaluatorAllowed": False,
        },
        "downstreamSentinelRule": (
            "use_final_unit_f_candidate_only_if_structurally_valid_and_pattern_simulation_"
            "render_binding_bytes_descend_from_pr43_else_use_pr43_candidate_"
            "candidate.d0_exact_fitted_topology_v2.060e8d4aaaa7e82eddb75880"
        ),
        "cohortRepresentativeRule": "evaluator_ordinal_zero_identity_independent_not_metric_ranked",
        "implementationFiles": _implementation_inventory(root),
        "evaluatorIdentitiesRealized": False,
        "targetContentsMounted": False,
        "lockHash": "",
    }
    lock["lockHash"] = _hash({**lock, "lockHash": ""})
    write_canonical_json(target / "development_draw_transcript.json", transcript)
    write_canonical_json(target / "development_summary.json", {"routes": route_summaries})
    write_canonical_json(target / "development_lock.json", lock)
    return lock


def build_source_evidence(identity: RealizedIdentity) -> dict[str, Any]:
    captures: dict[str, SourceCapture] = {}
    for role in ("front", "rear"):
        captures[role] = render_source_capture(
            identity.parameters,
            identity.appearance,
            identity.capture[role],
            role=role,
        )
    front = captures["front"]
    appearance = _measure_appearance(front)
    return {
        "front": source_features(front, role="front"),
        "rear": source_features(captures["rear"], role="rear"),
        "appearanceFeatures": appearance,
        "png": {role: capture.png for role, capture in captures.items()},
    }


def contestant_input(opaque_id: str, source: Mapping[str, Any], route: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"schemaVersion": 1, "opaqueId": opaque_id, "garmentClass": "tshirt"}
    if route in ROUTES[2:]:
        payload["sourceEvidence"] = {key: value for key, value in source.items() if key != "png"}
    return payload


def _development_config(identities: list[RealizedIdentity]) -> dict[str, Any]:
    prior = default_prior()
    no_pixel = {
        name: median(identity.parameters[name] for identity in identities)
        for name in OBSERVABLE_PARAMETERS
    }
    no_pixel.update({name: prior[name] for name in prior if name not in no_pixel})
    coverages = [
        build_source_evidence(identity)["front"]["maskCoverage"] for identity in identities
    ]
    return {
        "schemaVersion": 1,
        "metadataPrior": prior,
        "noPixelPrior": no_pixel,
        "sourceFitterBodyEase": 0.045,
        "developmentMaskCoverageMedian": median(coverages),
        "appearancePrior": {
            "baseColorSrgb": [92, 104, 119],
            "logoShape": "none",
            "logoCenterNormalized": [0.5, 0.5],
            "logoScaleNormalized": 0.1,
            "logoColorSrgb": [238, 231, 214],
            "neckShape": "crew",
        },
    }


def _measure_appearance(capture: SourceCapture) -> dict[str, Any]:
    image = decode_png_rgba(capture.png)
    logo_colour = (238, 231, 214)
    logo_pixels = [
        index
        for index in range(image.width * image.height)
        if tuple(image.rgba[index * 4 : index * 4 + 3]) == logo_colour
    ]
    landmarks = capture.landmarks
    chest_half = landmarks["hem.right"][0] - landmarks["hem.center"][0]
    if logo_pixels:
        xs = [index % image.width for index in logo_pixels]
        ys = [index // image.width for index in logo_pixels]
        cx = (sum(xs) / len(xs) + 0.5) / image.width
        cy = (sum(ys) / len(ys) + 0.5) / image.height
        width = (max(xs) - min(xs) + 1) / image.width
        height = (max(ys) - min(ys) + 1) / image.height
        fill = len(logo_pixels) / max(1, (max(xs) - min(xs) + 1) * (max(ys) - min(ys) + 1))
        if width / max(height, 1e-9) > 1.8:
            shape, scale = "bar", width / 1.4
        elif fill < 0.66:
            shape, scale = "diamond", width / 1.25
        else:
            shape, scale = "circle", width
        u = 0.5 + (cx - landmarks["hem.center"][0]) / max(1e-9, chest_half * 1.55)
        v = (cy - landmarks["neck.center"][1]) / max(
            1e-9, landmarks["hem.center"][1] - landmarks["neck.center"][1]
        )
    else:
        shape, scale, u, v = "none", 0.1, 0.5, 0.5
    return {
        "baseColorSrgb": mode_colour(image),
        "logoShape": shape,
        "logoCenterNormalized": [round(u, 6), round(v, 6)],
        "logoScaleNormalized": round(scale, 6),
        "logoColorSrgb": list(logo_colour),
        "neckShape": "crew",
    }


def _persist_development_identity(
    target: Path,
    identity: RealizedIdentity,
    source: Mapping[str, Any],
) -> dict[str, Any]:
    identity_root = target / "development" / identity.opaque_id
    png_records = []
    for role, payload in source["png"].items():
        path = identity_root / f"{role}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        png_records.append(
            {"role": role, "path": path.relative_to(target).as_posix(), "sha256": sha256_file(path)}
        )
    source_payload = {key: value for key, value in source.items() if key != "png"}
    write_canonical_json(identity_root / "source_evidence.json", source_payload)
    write_canonical_json(identity_root / "target.json", identity.target_record())
    return {
        "opaqueId": identity.opaque_id,
        "ordinal": identity.ordinal,
        "stratum": identity.stratum,
        "minimumPriorDistanceRequired": 0.15,
        "sourceFiles": png_records,
        "sourceEvidenceHash": _hash(source_payload),
        "targetCommitment": identity.target_commitment,
        "targetHash": sha256_file(identity_root / "target.json"),
    }


def _route_summaries(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for route in ROUTES:
        records = [item for item in results if item["routeId"] == route]
        errors = [float(item["metrics"]["macroNormalizedError"]) for item in records]
        summaries.append(
            {
                "routeId": route,
                "identityCount": len(records),
                "medianMacroNormalizedError": round(median(errors), 9),
                "meanMacroNormalizedError": round(math.fsum(errors) / len(errors), 9),
                "worstNormalizedError": max(
                    float(item["metrics"]["worstNormalizedError"]) for item in records
                ),
            }
        )
    return summaries


def _absolute_thresholds() -> dict[str, Any]:
    return {
        "minimumPredictionCoverage": 14,
        "identityCountDenominator": 16,
        "maximumMedianMacroNormalizedObservableError": 0.10,
        "maximumWorstNormalizedObservableError": 0.25,
        "minimumMeanEvaluatorViewSilhouetteIoU": 0.30,
        "maximumBoundaryProxyError": 0.20,
        "maximumLandmarkProxyError": 0.14,
        "maximumReferenceRmsVertexErrorMeters": 0.08,
        "requiredPanels": 5,
        "requiredSeamsMinimum": 1,
        "requiredOpenings": [
            "opening.cuff.left",
            "opening.cuff.right",
            "opening.hem",
            "opening.neck",
        ],
        "appearance": {
            "minimumSilhouetteIoU": 0.30,
            "maximumForegroundSrgbMae": 0.12,
            "minimumLogoIoU": 0.02,
            "maximumLogoDisplacementNormalized": 0.14,
            "maximumLogoFalsePositiveFraction": 0.002,
            "requiredValidIdentityCount": 8,
        },
    }


def _implementation_inventory(root: Path) -> list[dict[str, Any]]:
    paths = sorted((root / "src/closy_forge/disjoint_benchmark_v1").glob("*.py")) + sorted(
        (root / "scripts").glob("*d0_disjoint_benchmark_v1*.py")
    )
    return [
        {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)} for path in paths
    ]


def _boxy_reference(prior: Mapping[str, float]) -> dict[str, float]:
    result = dict(prior)
    result.update({"garment_body_length": 0.62, "half_chest_width": 0.33, "sleeve_length": 0.22})
    return result


def _long_reference(prior: Mapping[str, float]) -> dict[str, float]:
    result = dict(prior)
    result.update({"garment_body_length": 0.77, "half_chest_width": 0.25, "sleeve_length": 0.30})
    return result


def _hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))
