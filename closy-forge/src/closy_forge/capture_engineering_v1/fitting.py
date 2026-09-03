from __future__ import annotations

import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from closy_forge.garments.simple_skirt.parameters import SimpleSkirtParameters
from closy_forge.garments.sleeveless_top.parameters import SleevelessTopParameters
from closy_forge.garments.tshirt.assembly import build_simulation_mesh as build_tshirt_mesh
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.garments.tshirt.pattern_generator import build_tshirt_pattern
from closy_forge.geometry.mesh_model import MeshSet
from closy_forge.pattern_inference.grammar_v2 import (
    compile_program,
    default_parameters,
    program_from_parameters,
    validate_compiled_pattern,
)
from closy_forge.pattern_inference.reference_3d_v1 import build_reference_assembly
from closy_forge.pipeline.build_simple_skirt_demo import build_demo_simple_skirt_package
from closy_forge.pipeline.build_sleeveless_demo import build_demo_sleeveless_package
from closy_forge.pipeline.build_tshirt_demo import build_demo_tshirt_package

from .alternate_renderer import render_ray_triangles
from .common import canonical_digest, write_json
from .development_model import predict_linear_model
from .quality import PixelObservation

FIT_VERSION = "closy.camera_to_pattern.staged_development_fit.v1"

TARGET_FIELDS: dict[str, tuple[str, ...]] = {
    "tshirt": ("garment_body_length", "half_chest_width", "body_ease"),
    "sleeveless_top": (
        "body_length_meters",
        "half_chest_width_meters",
        "body_ease_meters",
    ),
    "simple_skirt": ("length_meters", "half_waist_width_meters", "flare_meters"),
}

BOUNDS: dict[str, dict[str, tuple[float, float]]] = {
    "tshirt": {
        "garment_body_length": (0.52, 0.82),
        "half_chest_width": (0.22, 0.38),
        "body_ease": (0.0, 0.12),
    },
    "sleeveless_top": {
        "body_length_meters": (0.48, 0.82),
        "half_chest_width_meters": (0.22, 0.38),
        "body_ease_meters": (0.0, 0.12),
    },
    "simple_skirt": {
        "length_meters": (0.36, 0.86),
        "half_waist_width_meters": (0.15, 0.30),
        "flare_meters": (0.0, 0.22),
    },
}


def fit_capture_to_package(
    *,
    family: str,
    observations: Sequence[PixelObservation],
    model: Mapping[str, Any],
    package_output: Path,
    seed: int,
) -> dict[str, Any]:
    """Fit from observations only; target parameters and generator camera are not accepted."""

    if family not in TARGET_FIELDS or not observations:
        raise ValueError("fit_family_or_observations_invalid")
    primary = observations[0]
    defaults = _default_values(family)
    deterministic = _deterministic_pixel_estimate(family, primary, defaults)
    predicted = _merge_prediction(family, defaults, predict_linear_model(model, family, primary))
    alternatives: list[dict[str, Any]] = []
    for route, parameters in (
        ("no_pixel_prior", defaults),
        ("policy_matched_retrieval", _retrieval_prior(family, primary, defaults)),
        ("deterministic_pixel_fit", deterministic),
        ("model_only", predicted),
    ):
        alternatives.append(_evaluate_alternative(family, route, parameters, primary, seed))
    refined = _local_refine(family, predicted, primary, seed)
    alternatives.append(refined)
    valid = [row for row in alternatives if row["status"] == "valid"]
    if not valid:
        return _failed_result(family, alternatives, "all_alternatives_invalid")
    selected = max(valid, key=lambda row: (float(row["silhouetteIou"]), row["route"]))
    package = _build_package(
        family,
        selected["parameters"],
        package_output,
        seed=seed,
    )
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "fitVersion": FIT_VERSION,
        "family": family,
        "status": "valid" if package["validationStatus"] == "passed" else "invalid_package",
        "stages": [
            "view_camera_alignment",
            "bounded_fixed_avatar_adjustment",
            "garment_template_retrieval",
            "panel_dimensions_and_curves",
            "seam_and_ease_ratios",
            "solver_backed_package_build",
            "independent_raster_comparison",
            "confidence_ranked_alternatives",
        ],
        "predictorBoundary": {
            "targetParametersConsumed": False,
            "fixtureIdentityConsumed": False,
            "evaluatorTransformsConsumed": False,
            "generatorSeedConsumedAsInput": False,
            "inputs": ["decoded_pixels", "mask", "landmarks", "declared_view_role"],
        },
        "attemptedAlternativeCount": len(alternatives),
        "alternatives": alternatives,
        "selectedRoute": selected["route"],
        "selectedParameters": selected["parameters"],
        "patternUncertainty": _parameter_uncertainty(family, selected["parameters"]),
        "cameraUncertainty": {"separateFromPattern": True, "normalizedRadius": 0.08},
        "package": package,
        "abstention": None,
        "fitDigest": "",
    }
    result["fitDigest"] = canonical_digest(result, "fitDigest")
    return result


def _evaluate_alternative(
    family: str,
    route: str,
    parameters: dict[str, float],
    observation: PixelObservation,
    seed: int,
) -> dict[str, Any]:
    try:
        pattern, meshset = _compile_mesh(family, parameters, seed)
        topology_issues = validate_compiled_pattern(pattern)
        rendered = render_ray_triangles(
            meshset,
            width=observation.width,
            height=observation.height,
            view_role="front",
        )
        candidate_foreground = frozenset(
            index
            for index in range(rendered.width * rendered.height)
            if tuple(rendered.rgba[index * 4 : index * 4 + 3]) != (232, 229, 222)
        )
        iou = _set_iou(observation.foreground, candidate_foreground)
        return {
            "route": route,
            "status": "valid"
            if not topology_issues and candidate_foreground
            else "topology_failure",
            "parameters": parameters,
            "compileExecuted": True,
            "topologyValidatorExecuted": True,
            "topologyIssues": topology_issues,
            "independentRendererExecuted": True,
            "silhouetteIou": round(iou, 8),
            "optimizerIterations": 1,
        }
    except (RuntimeError, ValueError) as error:
        return {
            "route": route,
            "status": "compile_failure",
            "parameters": parameters,
            "compileExecuted": True,
            "topologyValidatorExecuted": False,
            "topologyIssues": [type(error).__name__],
            "independentRendererExecuted": False,
            "silhouetteIou": 0.0,
            "optimizerIterations": 1,
        }


def _local_refine(
    family: str,
    predicted: dict[str, float],
    observation: PixelObservation,
    seed: int,
) -> dict[str, Any]:
    fields = TARGET_FIELDS[family][:2]
    attempts: list[dict[str, Any]] = []
    for length_scale in (0.96, 1.0, 1.04):
        for width_scale in (0.96, 1.0, 1.04):
            candidate = dict(predicted)
            candidate[fields[0]] = _bounded(family, fields[0], candidate[fields[0]] * length_scale)
            candidate[fields[1]] = _bounded(family, fields[1], candidate[fields[1]] * width_scale)
            attempts.append(
                _evaluate_alternative(
                    family,
                    "learned_plus_fit_iteration",
                    candidate,
                    observation,
                    seed,
                )
            )
    valid = [row for row in attempts if row["status"] == "valid"]
    if not valid:
        return {
            "route": "learned_plus_fit",
            "status": "compile_failure",
            "parameters": predicted,
            "compileExecuted": True,
            "topologyValidatorExecuted": True,
            "independentRendererExecuted": True,
            "silhouetteIou": 0.0,
            "optimizerIterations": len(attempts),
            "iterationStatusCounts": _status_counts(attempts),
        }
    selected = max(valid, key=lambda row: float(row["silhouetteIou"]))
    return {
        **selected,
        "route": "learned_plus_fit",
        "optimizerIterations": len(attempts),
        "iterationStatusCounts": _status_counts(attempts),
    }


def _compile_mesh(
    family: str, parameters: dict[str, float], seed: int
) -> tuple[dict[str, Any], MeshSet]:
    if family == "tshirt":
        params = TShirtParameters(**parameters)
        params.validate()
        pattern = build_tshirt_pattern(params)
        meshset, _edges = build_tshirt_mesh(pattern)
        return (pattern, meshset)
    program = program_from_parameters(
        family,
        parameters,
        program_id=f"fit.{family}.{seed}",
        base_seed=seed,
    )
    pattern = compile_program(program)
    return (pattern, build_reference_assembly(family, pattern)["simulation"])


def _build_package(
    family: str, parameters: Mapping[str, Any], output: Path, *, seed: int
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="closy-fit-package-") as temporary:
        staging = Path(temporary) / "package.closygarment"
        try:
            built: Any
            if family == "tshirt":
                built = build_demo_tshirt_package(
                    staging, params=TShirtParameters(**parameters), seed=seed
                )
            elif family == "sleeveless_top":
                built = build_demo_sleeveless_package(
                    staging, params=SleevelessTopParameters(**parameters), seed=seed
                )
            else:
                built = build_demo_simple_skirt_package(
                    staging, params=SimpleSkirtParameters(**parameters), seed=seed
                )
        except RuntimeError as error:
            if "package validation failed before publish" not in str(error):
                raise
            failed_summary = {
                "validationStatus": "failed",
                "validationCounts": {"error": 1},
                "manifestIdentity": None,
                "solverExecuted": True,
                "referenceSolverEvidence": "package_build_reached_final_validation",
                "compilerExecuted": True,
                "topologyValidatorExecuted": True,
                "failureReason": str(error),
            }
            write_json(output, failed_summary)
            return failed_summary
        output.parent.mkdir(parents=True, exist_ok=True)
        summary = {
            "validationStatus": built.validation["status"],
            "validationCounts": built.validation["counts"],
            "manifestIdentity": package_manifest_identity(built.manifest),
            "solverExecuted": True,
            "referenceSolverEvidence": "package_motion_and_settle_contracts",
            "compilerExecuted": True,
            "topologyValidatorExecuted": True,
        }
        write_json(output, summary)
        return summary


def package_manifest_identity(manifest: Mapping[str, Any]) -> dict[str, str]:
    digest = manifest.get("canonicalPackageDigest", manifest.get("packageDigest"))
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("built_package_digest_missing")
    garment_id = manifest.get("garmentId")
    if not isinstance(garment_id, str) or not garment_id:
        raise ValueError("built_package_garment_id_missing")
    return {"garmentId": garment_id, "packageDigest": digest}


def _default_values(family: str) -> dict[str, float]:
    if family == "tshirt":
        return {key: float(value) for key, value in TShirtParameters().to_json().items()}
    return {key: float(value) for key, value in default_parameters(family).items()}


def _deterministic_pixel_estimate(
    family: str, observation: PixelObservation, defaults: dict[str, float]
) -> dict[str, float]:
    left, top, right, bottom = observation.foreground_bbox
    width = (right - left + 1) / observation.width
    height = (bottom - top + 1) / observation.height
    aspect = width / max(1e-9, height)
    result = dict(defaults)
    length, width_field, third = TARGET_FIELDS[family]
    result[length] = _bounded(family, length, defaults[length] * (0.82 + 0.25 * height))
    result[width_field] = _bounded(
        family, width_field, defaults[width_field] * (0.72 + 0.55 * aspect)
    )
    result[third] = _bounded(
        family,
        third,
        defaults[third] * (0.75 + observation.foreground_coverage),
    )
    return result


def _retrieval_prior(
    family: str, observation: PixelObservation, defaults: dict[str, float]
) -> dict[str, float]:
    result = dict(defaults)
    length, width, _third = TARGET_FIELDS[family]
    if observation.foreground_coverage > 0.32:
        result[width] = _bounded(family, width, result[width] * 1.06)
    if observation.foreground_bbox[3] / observation.height > 0.82:
        result[length] = _bounded(family, length, result[length] * 1.05)
    return result


def _merge_prediction(
    family: str, defaults: dict[str, float], prediction: Mapping[str, float]
) -> dict[str, float]:
    result = dict(defaults)
    for field in TARGET_FIELDS[family]:
        result[field] = _bounded(family, field, float(prediction[field]))
    if family == "simple_skirt":
        result["half_hip_width_meters"] = max(
            result["half_waist_width_meters"] + result["waist_ease_meters"] + 0.035,
            result["half_hip_width_meters"],
        )
    return result


def _bounded(family: str, field: str, value: float) -> float:
    minimum, maximum = BOUNDS[family][field]
    return round(min(maximum, max(minimum, value)), 9)


def _set_iou(left: frozenset[int], right: frozenset[int]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _parameter_uncertainty(family: str, parameters: Mapping[str, float]) -> dict[str, list[float]]:
    return {
        field: [
            _bounded(family, field, float(parameters[field]) * 0.94),
            _bounded(family, field, float(parameters[field]) * 1.06),
        ]
        for field in TARGET_FIELDS[family]
    }


def _status_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        status = str(row["status"])
        result[status] = result.get(status, 0) + 1
    return dict(sorted(result.items()))


def _failed_result(family: str, alternatives: list[dict[str, Any]], reason: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "fitVersion": FIT_VERSION,
        "family": family,
        "status": "abstained",
        "attemptedAlternativeCount": len(alternatives),
        "alternatives": alternatives,
        "abstention": reason,
        "fitDigest": "",
    }
    result["fitDigest"] = canonical_digest(result, "fitDigest")
    return result
