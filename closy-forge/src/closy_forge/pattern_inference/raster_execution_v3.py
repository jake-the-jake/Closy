from __future__ import annotations

import tempfile
import time
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.garments.button_shirt.parameters import ButtonShirtParameters
from closy_forge.garments.jacket_outerwear.parameters import JacketOuterwearParameters
from closy_forge.garments.layered_asymmetric.parameters import LayeredAsymmetricParameters
from closy_forge.garments.long_sleeved_top.parameters import LongSleevedTopParameters
from closy_forge.garments.simple_dress.parameters import SimpleDressParameters
from closy_forge.garments.simple_skirt.parameters import SimpleSkirtParameters
from closy_forge.garments.simple_trousers.parameters import SimpleTrousersParameters
from closy_forge.garments.sleeveless_top.parameters import SleevelessTopParameters
from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.pipeline.build_button_shirt_demo import build_demo_button_shirt_package
from closy_forge.pipeline.build_jacket_outerwear_demo import build_demo_jacket_outerwear_package
from closy_forge.pipeline.build_layered_asymmetric_demo import (
    build_demo_layered_asymmetric_package,
)
from closy_forge.pipeline.build_long_sleeved_demo import build_demo_long_sleeved_package
from closy_forge.pipeline.build_simple_dress_demo import build_demo_simple_dress_package
from closy_forge.pipeline.build_simple_skirt_demo import build_demo_simple_skirt_package
from closy_forge.pipeline.build_simple_trousers_demo import build_demo_simple_trousers_package
from closy_forge.pipeline.build_sleeveless_demo import build_demo_sleeveless_package

from .grammar_v2 import FAMILY_SPECS, compile_program, default_parameters, program_from_parameters
from .model_v2 import decode_prediction, predict_v2
from .raster_dataset_v3 import compare_compiled_pattern_rasters

EXECUTION_VERSION_V3 = "closy.raster_pattern_downstream_execution.synthetic_d0.v1"


@dataclass(frozen=True)
class _BuildSpec:
    parameter_type: type[Any]
    builder: Callable[..., Any]
    fit_path: str


_BUILD_SPECS = {
    "sleeveless_top": _BuildSpec(
        SleevelessTopParameters, build_demo_sleeveless_package, "fitting/sleeveless_fit.json"
    ),
    "long_sleeved_top": _BuildSpec(
        LongSleevedTopParameters,
        build_demo_long_sleeved_package,
        "fitting/long_sleeved_fit.json",
    ),
    "simple_skirt": _BuildSpec(
        SimpleSkirtParameters, build_demo_simple_skirt_package, "fitting/simple_skirt_fit.json"
    ),
    "simple_trousers": _BuildSpec(
        SimpleTrousersParameters,
        build_demo_simple_trousers_package,
        "fitting/simple_trousers_fit.json",
    ),
    "simple_dress": _BuildSpec(
        SimpleDressParameters, build_demo_simple_dress_package, "fitting/simple_dress_fit.json"
    ),
    "button_shirt": _BuildSpec(
        ButtonShirtParameters, build_demo_button_shirt_package, "fitting/button_shirt_fit.json"
    ),
    "jacket_outerwear": _BuildSpec(
        JacketOuterwearParameters,
        build_demo_jacket_outerwear_package,
        "fitting/jacket_outerwear_fit.json",
    ),
    "layered_asymmetric": _BuildSpec(
        LayeredAsymmetricParameters,
        build_demo_layered_asymmetric_package,
        "fitting/layered_asymmetric_fit.json",
    ),
}


def execute_raster_downstream_v3(bundle: dict[str, Any]) -> dict[str, Any]:
    records = []
    with tempfile.TemporaryDirectory(prefix="closy-raster-downstream-") as temporary:
        root = Path(temporary)
        for family_index, family in enumerate(FAMILY_SPECS):
            records.append(_execute_family(bundle, family, family_index, root))
    all_learned = all(record["learnedFitRun"] for record in records)
    all_packages = all(record["package"]["validation"] == "passed" for record in records)
    return {
        "schemaVersion": 1,
        "executionVersion": EXECUTION_VERSION_V3,
        "scope": "eight_predeclared_families_project_authored_synthetic_host_cpu",
        "familyCount": len(records),
        "records": records,
        "counterfactuals": _counterfactual_summary(records),
        "E1": {
            "status": "pass" if all_learned and all_packages else "partial",
            "allFamiliesLearnedAdaptation": all_learned,
            "allPackagesValidated": all_packages,
            "allCompiled": all(record["compiledPatternHash"] for record in records),
            "allSettled": all(record["package"]["settledStateHash"] for record in records),
            "allRerendered": all(record["rerender"]["viewCount"] == 4 for record in records),
        },
        "E2": {
            "status": "not_run",
            "reason": "fixed_template_retrieval_and_adaptation_only",
        },
        "claims": {
            "globalPhase9Complete": False,
            "realPhotoGeneralisation": False,
            "privateUserGeneralisation": False,
            "humanCorrectionEvidence": False,
        },
    }


def _execute_family(
    bundle: dict[str, Any], family: str, family_index: int, root: Path
) -> dict[str, Any]:
    test_ids = set(bundle["split"]["samples"]["test"])
    sample = next(
        item
        for item in bundle["dataset"]["samples"]
        if item["sampleId"] in test_ids and item["target"]["garmentFamily"] == family
    )
    prediction = predict_v2(bundle["model"], sample["input"])
    learned_selected = (
        prediction.get("status") == "predicted" and prediction.get("family") == family
    )
    if learned_selected:
        program, pattern = decode_prediction(
            prediction,
            program_id=f"learned.e1.{family}",
            base_seed=53_000 + family_index,
        )
        selection_reason = "learned_prediction"
    else:
        program = program_from_parameters(
            family,
            default_parameters(family),
            program_id=f"fallback.e1.{family}",
            base_seed=53_000 + family_index,
        )
        pattern = compile_program(program)
        selection_reason = "validated_template_fallback_after_wrong_or_deferred_prediction"
    target_program = next(
        item
        for item in bundle["dataset"]["programs"]
        if item["programId"] == sample["sourceProgramId"]
    )
    target_pattern = compile_program(target_program)
    baseline_program = program_from_parameters(
        family,
        default_parameters(family),
        program_id=f"baseline.e1.{family}",
        base_seed=53_000 + family_index,
    )
    baseline_pattern = compile_program(baseline_program)
    pattern_hash = _hash(pattern)
    baseline_hash = _hash(baseline_pattern)
    learned_fit_run = bool(learned_selected and pattern_hash != baseline_hash)
    package_dir = root / f"{family}.closygarment"
    spec = _BUILD_SPECS[family]
    params = spec.parameter_type(**program["parameters"])
    wall_start = time.perf_counter_ns()
    cpu_start = time.process_time_ns()
    result = spec.builder(package_dir, params=params, seed=53_000 + family_index)
    cpu_ns = time.process_time_ns() - cpu_start
    wall_ns = time.perf_counter_ns() - wall_start
    settled = read_json(package_dir / "simulation" / "settled_state.json")
    fit = read_json(package_dir / spec.fit_path)
    rerender_root = root / f"rerender-{family}"
    rerender_root.mkdir(parents=True, exist_ok=True)
    rerender = compare_compiled_pattern_rasters(pattern, target_pattern, work_root=rerender_root)
    counterfactual = _counterfactual(
        pattern, baseline_pattern, target_pattern, family, rerender_root
    )
    return {
        "targetFamily": family,
        "heldOutSampleId": sample["sampleId"],
        "prediction": prediction,
        "selectionReason": selection_reason,
        "fallbackUsed": not learned_selected,
        "learnedFitRun": learned_fit_run,
        "modelOutputHash": _hash(prediction),
        "decodedProgramHash": _hash(program),
        "compiledPatternHash": pattern_hash,
        "baselinePatternHash": baseline_hash,
        "targetPatternHash": _hash(target_pattern),
        "package": {
            "validation": result.validation["status"],
            "canonicalPackageDigest": result.manifest.get(
                "canonicalPackageDigest", result.manifest.get("packageDigest")
            ),
            "manifestHash": sha256_file(package_dir / "manifest.json"),
            "settledStateHash": settled["meshContentHash"],
            "fitAccepted": bool(fit.get("accepted", False)),
            "deterministicFitterLearnedFitRun": bool(fit.get("learnedFitRun", False)),
        },
        "rerender": rerender,
        "counterfactual": counterfactual,
        "runtime": {
            "wallMilliseconds": round(wall_ns / 1_000_000, 6),
            "cpuMilliseconds": round(cpu_ns / 1_000_000, 6),
        },
    }


def _counterfactual(
    learned_pattern: dict[str, Any],
    fallback_pattern: dict[str, Any],
    target_pattern: dict[str, Any],
    family: str,
    root: Path,
) -> dict[str, Any]:
    spec = FAMILY_SPECS[family]
    corrupted_parameters = deepcopy(default_parameters(family))
    corrupted_parameters[spec.width_field] = round(
        min(
            float(corrupted_parameters[spec.width_field]) * 1.12,
            float(corrupted_parameters[spec.width_field]) + 0.04,
        ),
        9,
    )
    try:
        corrupted = compile_program(
            program_from_parameters(
                family,
                corrupted_parameters,
                program_id=f"counterfactual.corrupt.{family}",
                base_seed=79_000,
            )
        )
        corrupted_metrics = compare_compiled_pattern_rasters(
            corrupted, target_pattern, work_root=root / "corrupted"
        )
    except ValueError:
        corrupted_metrics = {"status": "rejected_invalid_parameter"}
    fallback_metrics = compare_compiled_pattern_rasters(
        fallback_pattern, target_pattern, work_root=root / "fallback"
    )
    return {
        "learnedGeometryDiffersFromFallback": _hash(learned_pattern) != _hash(fallback_pattern),
        "fallbackIdentified": True,
        "fallbackRerender": fallback_metrics,
        "corruptParameterDetected": corrupted_metrics.get("status") == "rejected_invalid_parameter"
        or corrupted_metrics.get("meanSilhouetteIoU") != fallback_metrics.get("meanSilhouetteIoU"),
        "corruptParameterRerender": corrupted_metrics,
    }


def _counterfactual_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "fallbackReplacementExplicit": all(
            record["counterfactual"]["fallbackIdentified"] for record in records
        ),
        "learnedWeightsOrOutputsChangeGeometry": any(
            record["counterfactual"]["learnedGeometryDiffersFromFallback"] for record in records
        ),
        "corruptParameterDetected": all(
            record["counterfactual"]["corruptParameterDetected"] for record in records
        ),
        "pixelsRemovedAblation": "evaluation.controls.pixelsDestroyed",
    }


def _hash(value: Any) -> str:
    return sha256_bytes(canonical_dumps(value).encode("utf-8"))
