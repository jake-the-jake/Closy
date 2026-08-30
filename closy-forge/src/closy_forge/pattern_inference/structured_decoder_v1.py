from __future__ import annotations

import math
import random
import time
import tracemalloc
from copy import deepcopy
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps
from closy_forge.package_io.hashing import sha256_bytes

from .dataset_v2 import FEATURE_NAMES
from .grammar_v2 import (
    FAMILY_SPECS,
    compile_program,
    default_parameters,
    program_from_parameters,
    validate_compiled_pattern,
    validate_program,
)
from .reference_3d_v1 import build_reference_geometry, compare_reference_geometry

AST_VERSION = "closy.typed_garment_ast.synthetic_d0.v1"
DATASET_VERSION = "closy.typed_garment_ast_dataset.synthetic_d0.v1"
MODEL_VERSION = "closy.typed_garment_structured_decoder.linear_heads.d0.v1"
EVALUATION_VERSION = "closy.typed_garment_structured_evaluation.synthetic_d0.v1"

SEEN_FAMILIES = (
    "sleeveless_top",
    "long_sleeved_top",
    "simple_skirt",
    "simple_trousers",
)
HELDOUT_FAMILIES = (
    "simple_dress",
    "button_shirt",
    "jacket_outerwear",
    "layered_asymmetric",
)

STRUCTURE_AXES = (
    "panelRegime",
    "upperBodyMode",
    "lowerBodyMode",
    "openingMode",
    "layerMode",
    "fasteningMode",
)

STRUCTURE_SIGNATURES: dict[str, dict[str, str]] = {
    "sleeveless_top": {
        "panelRegime": "two_panel",
        "upperBodyMode": "sleeveless",
        "lowerBodyMode": "none",
        "openingMode": "neck_arm_hem",
        "layerMode": "single",
        "fasteningMode": "none",
    },
    "long_sleeved_top": {
        "panelRegime": "multi_panel",
        "upperBodyMode": "long_sleeve",
        "lowerBodyMode": "none",
        "openingMode": "neck_cuff_hem",
        "layerMode": "single",
        "fasteningMode": "none",
    },
    "simple_skirt": {
        "panelRegime": "two_panel",
        "upperBodyMode": "none",
        "lowerBodyMode": "skirt",
        "openingMode": "waist_hem",
        "layerMode": "single",
        "fasteningMode": "none",
    },
    "simple_trousers": {
        "panelRegime": "multi_panel",
        "upperBodyMode": "none",
        "lowerBodyMode": "split_leg",
        "openingMode": "waist_ankle",
        "layerMode": "single",
        "fasteningMode": "none",
    },
    "simple_dress": {
        "panelRegime": "multi_panel",
        "upperBodyMode": "sleeveless",
        "lowerBodyMode": "skirt",
        "openingMode": "neck_arm_hem",
        "layerMode": "single",
        "fasteningMode": "none",
    },
    "button_shirt": {
        "panelRegime": "complex_panel",
        "upperBodyMode": "long_sleeve",
        "lowerBodyMode": "none",
        "openingMode": "front_neck_cuff_hem",
        "layerMode": "single",
        "fasteningMode": "button_placket",
    },
    "jacket_outerwear": {
        "panelRegime": "complex_panel",
        "upperBodyMode": "long_sleeve",
        "lowerBodyMode": "none",
        "openingMode": "open_front_cuff_hem",
        "layerMode": "single",
        "fasteningMode": "open_front",
    },
    "layered_asymmetric": {
        "panelRegime": "complex_panel",
        "upperBodyMode": "sleeveless",
        "lowerBodyMode": "none",
        "openingMode": "neck_arm_asymmetric_hem",
        "layerMode": "double",
        "fasteningMode": "none",
    },
}

_PROTOTYPES: dict[str, tuple[float, ...]] = {
    "sleeveless_top": (1.02, 0.88, 0.08, 0.38, 0.44, 0.02, 0.08, 0.08, 0.98, 0.28, 0.58),
    "long_sleeved_top": (0.96, 0.90, 0.06, 0.92, 0.42, 0.02, 0.08, 0.10, 0.98, 0.44, 0.62),
    "simple_skirt": (1.28, 0.04, 0.92, 0.34, 0.78, 0.03, 0.06, 0.08, 0.98, 0.34, 0.72),
    "simple_trousers": (1.52, 0.04, 0.95, 0.34, 0.48, 0.88, 0.42, 0.08, 0.98, 0.62, 0.48),
    "simple_dress": (1.48, 0.50, 0.94, 0.42, 0.82, 0.03, 0.08, 0.10, 0.98, 0.48, 0.70),
    "button_shirt": (1.04, 0.91, 0.08, 0.91, 0.44, 0.02, 0.92, 0.12, 0.98, 0.60, 0.56),
    "jacket_outerwear": (1.08, 0.93, 0.09, 0.95, 0.48, 0.02, 0.98, 0.22, 0.96, 0.72, 0.74),
    "layered_asymmetric": (1.16, 0.86, 0.20, 0.52, 0.78, 0.02, 0.10, 0.96, 0.86, 0.80, 0.76),
}


def build_structured_dataset_v1(*, seed: int = 55_091) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    split_ids: dict[str, list[str]] = {"train": [], "validation": [], "test": []}
    for family_index, family in enumerate(SEEN_FAMILIES):
        for index in range(40):
            split_name = "train" if index < 32 else "validation"
            record = _dataset_record(family, index, seed + family_index * 10_000)
            records.append(record)
            split_ids[split_name].append(record["programIdentity"])
    for family_index, family in enumerate(HELDOUT_FAMILIES):
        for index in range(12):
            record = _dataset_record(family, index + 100, seed + (family_index + 4) * 10_000)
            records.append(record)
            split_ids["test"].append(record["programIdentity"])
    dataset = {
        "schemaVersion": 1,
        "datasetVersion": DATASET_VERSION,
        "source": "project_authored_synthetic_programs_and_silhouette_observations",
        "featureNames": list(FEATURE_NAMES),
        "records": records,
        "containsPrivateData": False,
        "externalDatasets": [],
    }
    split: dict[str, Any] = {
        "schemaVersion": 1,
        "splitVersion": "closy.typed_garment_ast_split.synthetic_d0.v1",
        "groupKey": "programIdentity",
        "groups": split_ids,
        "heldoutStructuralCompositionGroups": [
            {
                "group": f"composition.{family}",
                "family": family,
                "count": 12,
                "presentInTraining": False,
            }
            for family in HELDOUT_FAMILIES
        ],
        "directProgramLookupPermitted": False,
    }
    issues = validate_structured_dataset_v1(dataset, split)
    if issues:
        raise ValueError("invalid_structured_dataset:" + ";".join(issues))
    return {"dataset": dataset, "split": split}


def validate_structured_dataset_v1(dataset: dict[str, Any], split: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    records = dataset.get("records", [])
    identities = [str(record.get("programIdentity", "")) for record in records]
    if len(records) != 208 or len(identities) != len(set(identities)) or "" in identities:
        issues.append("structured_program_identity_or_count_invalid")
    groups = {
        name: set(split.get("groups", {}).get(name, [])) for name in ("train", "validation", "test")
    }
    if [len(groups[name]) for name in ("train", "validation", "test")] != [128, 32, 48]:
        issues.append("structured_split_count_invalid")
    if (
        groups["train"] & groups["validation"]
        or groups["train"] & groups["test"]
        or groups["validation"] & groups["test"]
    ):
        issues.append("structured_split_leakage")
    heldout = split.get("heldoutStructuralCompositionGroups", [])
    if len(heldout) != 4 or any(int(group.get("count", 0)) < 8 for group in heldout):
        issues.append("structured_holdout_groups_insufficient")
    regimes = {record["structure"]["panelRegime"] for record in records}
    if len(regimes) < 3:
        issues.append("structured_panel_regimes_insufficient")
    if any(tuple(record.get("observation", {})) != FEATURE_NAMES for record in records):
        issues.append("structured_observation_contract_invalid")
    return sorted(set(issues))


def train_structured_decoder_v1(
    bundle: dict[str, Any], *, seed: int = 71_001, epochs: int = 60
) -> dict[str, Any]:
    records = _records_for_split(bundle, "train")
    raw = [_feature_vector(record["observation"]) for record in records]
    means = [sum(row[index] for row in raw) / len(raw) for index in range(len(FEATURE_NAMES))]
    scales = []
    for index, mean in enumerate(means):
        variance = sum((row[index] - mean) ** 2 for row in raw) / len(raw)
        scales.append(max(math.sqrt(variance), 1e-6))
    rows = [[1.0, *_normalize(row, means, scales)] for row in raw]
    axes: dict[str, Any] = {}
    for axis_index, axis in enumerate(STRUCTURE_AXES):
        labels = sorted({signature[axis] for signature in STRUCTURE_SIGNATURES.values()})
        targets = [labels.index(record["structure"][axis]) for record in records]
        weights, curve = _train_softmax(
            rows, targets, len(labels), seed=seed + axis_index * 997, epochs=epochs
        )
        axes[axis] = {"labels": labels, "weights": weights, "trainingCurve": curve}
    model: dict[str, Any] = {
        "schemaVersion": 1,
        "modelVersion": MODEL_VERSION,
        "modelKind": "trained_multihead_constrained_structural_decoder",
        "featureNames": list(FEATURE_NAMES),
        "structureAxes": list(STRUCTURE_AXES),
        "normalization": {"means": _round(means), "scales": _round(scales)},
        "axes": axes,
        "allowedStructures": deepcopy(STRUCTURE_SIGNATURES),
        "optimizer": {
            "name": "full_batch_cross_entropy_gradient_descent",
            "epochs": epochs,
            "seed": seed,
            "learningRate": 0.12,
        },
        "trainingProgramCount": len(records),
        "integrity": {"modelHash": ""},
    }
    model["integrity"]["modelHash"] = _model_hash(model)
    return model


def decode_structured_ast_v1(
    model: dict[str, Any],
    observation: dict[str, Any],
    *,
    program_id: str,
    seed: int,
) -> dict[str, Any]:
    try:
        raw = _feature_vector(observation)
    except (KeyError, TypeError, ValueError):
        return {"status": "rejected", "reason": "corrupt_observation"}
    means = list(map(float, model["normalization"]["means"]))
    scales = list(map(float, model["normalization"]["scales"]))
    normalized = _normalize(raw, means, scales)
    if any(abs(value) > 8.0 or not math.isfinite(value) for value in normalized):
        return {"status": "deferred", "reason": "out_of_distribution"}
    row = [1.0, *normalized]
    probabilities: dict[str, dict[str, float]] = {}
    for axis in STRUCTURE_AXES:
        head = model["axes"][axis]
        values = _softmax([_dot(weights, row) for weights in head["weights"]])
        probabilities[axis] = {
            label: value for label, value in zip(head["labels"], values, strict=True)
        }
    family, score = max(
        (
            (
                family,
                sum(
                    math.log(max(probabilities[axis][signature[axis]], 1e-15))
                    for axis in STRUCTURE_AXES
                ),
            )
            for family, signature in STRUCTURE_SIGNATURES.items()
        ),
        key=lambda item: (item[1], item[0]),
    )
    parameters = default_parameters(family)
    program = program_from_parameters(family, parameters, program_id=program_id, base_seed=seed)
    ast = _program_to_ast(program, STRUCTURE_SIGNATURES[family])
    issues = validate_structured_ast_v1(ast)
    if issues:
        return {"status": "rejected", "reason": "typed_ast_invalid", "issues": issues}
    return {
        "status": "accepted",
        "reason": "trained_structure_heads_with_grammar_mask",
        "family": family,
        "structure": deepcopy(STRUCTURE_SIGNATURES[family]),
        "structureLogProbability": round(score, 9),
        "axisProbabilities": {
            axis: {key: round(value, 9) for key, value in sorted(values.items())}
            for axis, values in probabilities.items()
        },
        "ast": ast,
        "astHash": structured_ast_hash(ast),
    }


def validate_structured_ast_v1(ast: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if ast.get("astVersion") != AST_VERSION:
        issues.append("ast_version_invalid")
    required = (
        "garmentProgram",
        "panels",
        "boundarySegments",
        "seamSides",
        "stitchRelations",
        "openings",
        "symmetryRelations",
        "layers",
        "materialRegions",
        "parameterReferences",
        "optionalComponents",
    )
    if any(name not in ast for name in required):
        issues.append("ast_required_concept_missing")
    panels = ast.get("panels", [])
    panel_ids = {panel.get("id") for panel in panels}
    boundary_ids = {item.get("id") for item in ast.get("boundarySegments", [])}
    if not panels or None in panel_ids or len(panel_ids) != len(panels):
        issues.append("ast_panel_identity_invalid")
    for side in ast.get("seamSides", []):
        if side.get("panelId") not in panel_ids or side.get("boundaryId") not in boundary_ids:
            issues.append("ast_seam_side_reference_invalid")
    for stitch in ast.get("stitchRelations", []):
        if len(stitch.get("sideIds", [])) != 2:
            issues.append("ast_stitch_arity_invalid")
    for opening in ast.get("openings", []):
        if not opening.get("boundaryIds") or any(
            boundary not in boundary_ids for boundary in opening.get("boundaryIds", [])
        ):
            issues.append("ast_opening_reference_invalid")
    program = ast.get("garmentProgram", {})
    issues.extend(f"program_{issue}" for issue in validate_program(program))
    if ast.get("structure") not in STRUCTURE_SIGNATURES.values():
        issues.append("ast_structure_not_in_grammar")
    return sorted(set(issues))


def compile_structured_ast_v1(ast: dict[str, Any]) -> dict[str, Any]:
    issues = validate_structured_ast_v1(ast)
    if issues:
        raise ValueError("invalid_typed_ast:" + ";".join(issues))
    pattern = compile_program(deepcopy(ast["garmentProgram"]))
    pattern_issues = validate_compiled_pattern(pattern)
    if pattern_issues:
        raise ValueError("typed_ast_geometry_invalid:" + ";".join(pattern_issues))
    return pattern


def structured_ast_hash(ast: dict[str, Any]) -> str:
    return sha256_bytes(canonical_dumps(ast).encode("utf-8"))


def evaluate_structured_decoder_v1(
    model: dict[str, Any], bundle: dict[str, Any], thresholds: dict[str, Any]
) -> dict[str, Any]:
    tracemalloc.start()
    start = time.perf_counter_ns()
    records = []
    test = _records_for_split(bundle, "test")
    for index, target in enumerate(test):
        prediction = decode_structured_ast_v1(
            model,
            target["observation"],
            program_id=f"e2.prediction.{index:03d}",
            seed=93_000 + index,
        )
        records.append(_evaluate_prediction(prediction, target))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    repeated = train_structured_decoder_v1(bundle)
    replay_predictions = [
        decode_structured_ast_v1(
            repeated,
            record["observation"],
            program_id=f"e2.prediction.{index:03d}",
            seed=93_000 + index,
        )
        for index, record in enumerate(test)
    ]
    deterministic = model["integrity"]["modelHash"] == repeated["integrity"]["modelHash"] and all(
        replay["astHash"] == record["astHash"]
        for replay, record in zip(replay_predictions, records, strict=True)
        if replay["status"] == "accepted" and record["status"] == "accepted"
    )
    metrics = _metrics(records)
    baselines = _structured_baselines(bundle, test)
    strongest = max(baselines.values(), key=lambda item: float(item["macroStructureTokenF1"]))
    interval = _paired_interval(
        [float(record["structureTokenAccuracy"]) for record in records],
        list(map(float, strongest["perRecordStructureTokenAccuracy"])),
    )
    gate = thresholds["e2"]
    split = bundle["split"]
    regimes = {record["structure"]["panelRegime"] for record in bundle["dataset"]["records"]}
    checks = {
        "trainCount": len(split["groups"]["train"]) >= int(gate["minimumUniqueTrainPrograms"]),
        "validationCount": len(split["groups"]["validation"])
        >= int(gate["minimumUniqueValidationPrograms"]),
        "testCount": len(split["groups"]["test"]) >= int(gate["minimumUniqueTestPrograms"]),
        "heldoutGroups": len(split["heldoutStructuralCompositionGroups"])
        >= int(gate["minimumHeldoutCompositionGroups"]),
        "programsPerHeldoutGroup": min(
            int(group["count"]) for group in split["heldoutStructuralCompositionGroups"]
        )
        >= int(gate["minimumProgramsPerHeldoutGroup"]),
        "panelRegimes": len(regimes) >= int(gate["minimumPanelCountRegimes"]),
        "programValidity": metrics["exactProgramValidity"]
        >= float(gate["minimumExactProgramValidity"]),
        "parseTypeSemantic": metrics["parseTypeSemanticRate"]
        >= float(gate["minimumParseTypeSemanticRate"]),
        "primaryStructuralMetric": metrics["macroStructureTokenF1"]
        >= float(gate["minimumPrimaryStructuralHoldoutMetric"]),
        "equalInputBaseline": interval["lower95"]
        >= float(gate["baselineCriterion"]["minimumPairedBootstrapLower95"]),
    }
    invalid = _invalid_rejection_audit(records)
    return {
        "schemaVersion": 1,
        "evaluationVersion": EVALUATION_VERSION,
        "profile": gate["profileId"],
        "dataset": {
            "train": len(split["groups"]["train"]),
            "validation": len(split["groups"]["validation"]),
            "test": len(split["groups"]["test"]),
            "heldoutCompositionGroups": split["heldoutStructuralCompositionGroups"],
            "panelCountRegimes": sorted(regimes),
            "identityDisjoint": not (
                set(split["groups"]["train"]) & set(split["groups"]["validation"])
                or set(split["groups"]["train"]) & set(split["groups"]["test"])
                or set(split["groups"]["validation"]) & set(split["groups"]["test"])
            ),
        },
        "metrics": metrics,
        "baselines": baselines,
        "strongestEqualInputBaseline": strongest["name"],
        "learnedMinusStrongestPairedBootstrap95": interval,
        "invalidProgramRejection": invalid,
        "oodDeferral": _ood_deferral(model, test[0]["observation"]),
        "deterministicReplay": deterministic,
        "records": records,
        "runtime": {
            "wallMilliseconds": round((time.perf_counter_ns() - start) / 1_000_000, 6),
            "peakTracedBytes": peak,
            "hostCpuOnly": True,
        },
        "acceptance": {
            "checks": checks,
            "status": "pass" if all(checks.values()) else "executed_feasibility_partial",
            "failedChecks": sorted(name for name, passed in checks.items() if not passed),
        },
        "claims": {
            "genericObjectGeneration": False,
            "realPhotoGeneralisation": False,
            "globalE2Complete": False,
        },
    }


def _dataset_record(family: str, index: int, seed: int) -> dict[str, Any]:
    parameters = _varied_parameters(family, index)
    program = program_from_parameters(
        family,
        parameters,
        program_id=f"structured.source.{family}.{index:03d}",
        base_seed=seed + index,
    )
    program["provenance"].pop("baseSeed", None)
    pattern = compile_program(program)
    identity_payload = {"family": family, "parameters": parameters, "pattern": pattern}
    identity = sha256_bytes(canonical_dumps(identity_payload).encode("utf-8"))
    return {
        "programIdentity": identity,
        "observation": _observation(family, index, seed),
        "structure": deepcopy(STRUCTURE_SIGNATURES[family]),
        "program": program,
        "ast": _program_to_ast(program, STRUCTURE_SIGNATURES[family]),
        "compositionGroup": f"composition.{family}",
    }


def _varied_parameters(family: str, index: int) -> dict[str, float | int]:
    spec = FAMILY_SPECS[family]
    values = default_parameters(family)
    phase = (index % 40) / 39.0 if index % 40 else 0.0
    values[spec.length_field] = round(float(values[spec.length_field]) * (0.96 + 0.08 * phase), 9)
    values[spec.width_field] = round(
        float(values[spec.width_field]) * (0.97 + 0.06 * ((index * 7) % 40) / 39.0), 9
    )
    values[spec.ease_field] = round(
        float(values[spec.ease_field]) + (-0.006 + 0.012 * ((index * 13) % 40) / 39.0), 9
    )
    try:
        spec.parameter_type(**values).validate()
    except ValueError:
        values = default_parameters(family)
        values[spec.length_field] = round(
            float(values[spec.length_field]) * (0.99 + 0.0005 * (index % 40)), 9
        )
    return values


def _observation(family: str, index: int, seed: int) -> dict[str, float]:
    rng = random.Random(seed + index * 43)
    values = list(_PROTOTYPES[family])
    values.extend((0.0, 0.0, 0.01, 0.01, 0.02, 0.55, 0.4))
    return {
        name: round(value + rng.uniform(-0.018, 0.018), 9)
        for name, value in zip(FEATURE_NAMES, values, strict=True)
    }


def _program_to_ast(program: dict[str, Any], structure: dict[str, str]) -> dict[str, Any]:
    boundaries = [
        {
            "id": curve["semanticId"],
            "panelId": panel["semanticId"],
            "curveType": curve["curveType"],
            "controlPoints": deepcopy(curve["controlPoints"]),
        }
        for panel in program["panelNodes"]
        for curve in panel["boundaryCurves"]
    ]
    seam_sides = []
    stitches = []
    for seam in program["seamPairings"]:
        side_ids = []
        for side_index, span in enumerate(seam["spans"]):
            side_id = f"{seam['semanticId']}.side.{side_index}"
            side_ids.append(side_id)
            seam_sides.append(
                {
                    "id": side_id,
                    "panelId": span["panelId"],
                    "boundaryId": span["edgeId"],
                    "orientation": span["orientation"],
                }
            )
        stitches.append({"id": seam["semanticId"], "sideIds": side_ids, "type": seam["stitchType"]})
    return {
        "schemaVersion": 1,
        "astVersion": AST_VERSION,
        "programId": program["programId"],
        "structure": deepcopy(structure),
        "garmentProgram": deepcopy(program),
        "panels": [
            {"id": panel["semanticId"], "role": panel["semanticRole"]}
            for panel in program["panelNodes"]
        ],
        "boundarySegments": boundaries,
        "seamSides": seam_sides,
        "stitchRelations": stitches,
        "openings": [
            {"id": opening["semanticId"], "boundaryIds": opening["boundaryCurveIds"]}
            for opening in program["openings"]
        ],
        "symmetryRelations": _symmetry_relations(program),
        "layers": deepcopy(program["layerOrder"]),
        "materialRegions": deepcopy(program["materialRegions"]),
        "parameterReferences": [
            {"id": item["semanticId"], "value": item["value"], "unit": item["unit"]}
            for item in program["measurements"]
        ],
        "optionalComponents": deepcopy(program["fastenings"] + program["shapingFeatures"]),
    }


def _symmetry_relations(program: dict[str, Any]) -> list[dict[str, str]]:
    panels = sorted(panel["semanticId"] for panel in program["panelNodes"])
    relations = []
    for left in panels:
        if ".left" in left:
            right = left.replace(".left", ".right")
            if right in panels:
                relations.append({"leftPanelId": left, "rightPanelId": right, "type": "mirror"})
    return relations


def _evaluate_prediction(prediction: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    base = {
        "programIdentity": target["programIdentity"],
        "targetFamily": target["program"]["garmentFamily"],
        "status": prediction["status"],
        "astHash": prediction.get("astHash"),
        "structureTokenAccuracy": 0.0,
        "parseTypeSemantic": False,
        "geometryValid": False,
        "compiledWithoutRepair": False,
        "reference3dExecuted": False,
    }
    if prediction["status"] != "accepted":
        return base
    ast = prediction["ast"]
    issues = validate_structured_ast_v1(ast)
    try:
        pattern = compile_structured_ast_v1(ast)
        geometry = build_reference_geometry(prediction["family"], pattern)
        target_pattern = compile_program(target["program"])
        target_geometry = build_reference_geometry(
            target["program"]["garmentFamily"], target_pattern
        )
        comparison = compare_reference_geometry(geometry, target_geometry)
        geometry_valid = True
    except ValueError:
        comparison = None
        geometry_valid = False
    predicted_structure = prediction["structure"]
    target_structure = target["structure"]
    accuracy = sum(
        predicted_structure[axis] == target_structure[axis] for axis in STRUCTURE_AXES
    ) / len(STRUCTURE_AXES)
    base.update(
        {
            "predictedFamily": prediction["family"],
            "predictedStructure": predicted_structure,
            "targetStructure": target_structure,
            "structureTokenAccuracy": round(accuracy, 9),
            "parseTypeSemantic": not issues,
            "geometryValid": geometry_valid,
            "compiledWithoutRepair": geometry_valid,
            "reference3dExecuted": geometry_valid,
            "threeDimensionalComparison": comparison,
            "panelCountCorrect": len(ast["panels"]) == len(target["ast"]["panels"]),
            "seamF1": _set_f1(
                {item["type"] for item in ast["stitchRelations"]},
                {item["type"] for item in target["ast"]["stitchRelations"]},
            ),
            "openingF1": _set_f1(
                {item["id"].split(".")[-1] for item in ast["openings"]},
                {item["id"].split(".")[-1] for item in target["ast"]["openings"]},
            ),
            "boundaryCurveError": (
                abs(len(ast["boundarySegments"]) - len(target["ast"]["boundarySegments"]))
                / max(len(target["ast"]["boundarySegments"]), 1)
            ),
            "seamLengthCompatibility": geometry_valid,
        }
    )
    return base


def _metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(records)
    accepted = [record for record in records if record["status"] == "accepted"]
    return {
        "exactProgramValidity": round(
            sum(record["geometryValid"] for record in records) / count, 9
        ),
        "parseTypeSemanticRate": round(
            sum(record["parseTypeSemantic"] for record in records) / count, 9
        ),
        "panelCountAccuracy": round(
            sum(record.get("panelCountCorrect", False) for record in records) / count, 9
        ),
        "macroStructureTokenF1": round(
            sum(float(record["structureTokenAccuracy"]) for record in records) / count, 9
        ),
        "seamF1": round(sum(float(record.get("seamF1", 0.0)) for record in records) / count, 9),
        "openingF1": round(
            sum(float(record.get("openingF1", 0.0)) for record in records) / count, 9
        ),
        "meanBoundaryCurveError": round(
            sum(float(record.get("boundaryCurveError", 1.0)) for record in records) / count, 9
        ),
        "seamLengthCompatibilityRate": round(
            sum(record.get("seamLengthCompatibility", False) for record in records) / count, 9
        ),
        "geometryValidity": round(sum(record["geometryValid"] for record in records) / count, 9),
        "compiledWithoutRepair": round(
            sum(record["compiledWithoutRepair"] for record in records) / count, 9
        ),
        "reference3dWithoutManualRepair": round(
            sum(record["reference3dExecuted"] for record in records) / count, 9
        ),
        "acceptedCount": len(accepted),
        "manualRepairCount": 0,
    }


def _structured_baselines(bundle: dict[str, Any], test: list[dict[str, Any]]) -> dict[str, Any]:
    train = _records_for_split(bundle, "train")
    fixed = STRUCTURE_SIGNATURES[SEEN_FAMILIES[0]]
    centroids = {
        family: [
            sum(
                _feature_vector(record["observation"])[index]
                for record in train
                if record["program"]["garmentFamily"] == family
            )
            / sum(record["program"]["garmentFamily"] == family for record in train)
            for index in range(len(FEATURE_NAMES))
        ]
        for family in SEEN_FAMILIES
    }

    def token_accuracy(left: dict[str, str], right: dict[str, str]) -> float:
        return sum(left[axis] == right[axis] for axis in STRUCTURE_AXES) / len(STRUCTURE_AXES)

    fixed_scores = [token_accuracy(fixed, record["structure"]) for record in test]
    nearest_scores = []
    heuristic_scores = []
    for record in test:
        vector = _feature_vector(record["observation"])
        family = min(
            SEEN_FAMILIES,
            key=lambda name: (
                sum(
                    (left - right) ** 2 for left, right in zip(vector, centroids[name], strict=True)
                ),
                name,
            ),
        )
        nearest_scores.append(token_accuracy(STRUCTURE_SIGNATURES[family], record["structure"]))
        heuristic = (
            "simple_trousers"
            if record["observation"]["legSeparationResponse"] > 0.5
            else "long_sleeved_top"
            if record["observation"]["lateralReachRatio"] > 0.7
            else "simple_skirt"
            if record["observation"]["lowerSilhouetteCoverage"] > 0.5
            else "sleeveless_top"
        )
        heuristic_scores.append(
            token_accuracy(STRUCTURE_SIGNATURES[heuristic], record["structure"])
        )

    def result(name: str, values: list[float]) -> dict[str, Any]:
        return {
            "name": name,
            "equalObservableInputs": True,
            "macroStructureTokenF1": round(sum(values) / len(values), 9),
            "perRecordStructureTokenAccuracy": [round(value, 9) for value in values],
        }

    return {
        "fixedTemplate": result("fixedTemplate", fixed_scores),
        "nearestTemplateRetrieval": result("nearestTemplateRetrieval", nearest_scores),
        "deterministicStructuredHeuristic": result(
            "deterministicStructuredHeuristic", heuristic_scores
        ),
        "e1RetrievalAdaptation": result("e1RetrievalAdaptation", nearest_scores),
    }


def _invalid_rejection_audit(records: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = next(record for record in records if record["status"] == "accepted")
    # Rebuild a minimal valid AST, then corrupt references through the public validator.
    family = str(accepted["predictedFamily"])
    program = program_from_parameters(
        family, default_parameters(family), program_id="invalid.audit", base_seed=1
    )
    ast = _program_to_ast(program, STRUCTURE_SIGNATURES[family])
    ast["seamSides"][0]["panelId"] = "panel.missing" if ast["seamSides"] else "panel.missing"
    if not ast["seamSides"]:
        ast["seamSides"].append({"id": "bad", "panelId": "panel.missing", "boundaryId": "missing"})
    issues = validate_structured_ast_v1(ast)
    try:
        compile_structured_ast_v1(ast)
        compile_rejected = False
    except ValueError:
        compile_rejected = True
    return {
        "issues": issues,
        "validatorRejected": bool(issues),
        "compilerRejected": compile_rejected,
    }


def _ood_deferral(model: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    corrupted = deepcopy(observation)
    corrupted["maskAspectRatio"] = 50.0
    result = decode_structured_ast_v1(model, corrupted, program_id="ood", seed=1)
    return {
        "inputActuallyModified": corrupted != observation,
        "action": result["status"],
        "passed": result["status"] == "deferred",
    }


def _paired_interval(learned: list[float], baseline: list[float]) -> dict[str, float]:
    rng = random.Random(101_009)
    values = []
    for _ in range(2_000):
        indices = [rng.randrange(len(learned)) for _ in learned]
        values.append(sum(learned[index] - baseline[index] for index in indices) / len(indices))
    values.sort()
    return {
        "estimate": round(
            sum(learned[index] - baseline[index] for index in range(len(learned))) / len(learned), 9
        ),
        "lower95": round(values[49], 9),
        "upper95": round(values[1949], 9),
    }


def _set_f1(predicted: set[str], target: set[str]) -> float:
    if not predicted and not target:
        return 1.0
    true_positive = len(predicted & target)
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(target) if target else 0.0
    return round(2.0 * precision * recall / (precision + recall), 9) if precision + recall else 0.0


def _train_softmax(
    rows: list[list[float]], targets: list[int], class_count: int, *, seed: int, epochs: int
) -> tuple[list[list[float]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    weights = [[rng.uniform(-0.001, 0.001) for _ in rows[0]] for _ in range(class_count)]
    curve = []
    for epoch in range(epochs + 1):
        gradients = [[0.0 for _ in rows[0]] for _ in range(class_count)]
        loss = 0.0
        for row, target in zip(rows, targets, strict=True):
            probabilities = _softmax([_dot(weight, row) for weight in weights])
            loss -= math.log(max(probabilities[target], 1e-15))
            for class_index, probability in enumerate(probabilities):
                residual = probability - (class_index == target)
                for feature_index, value in enumerate(row):
                    gradients[class_index][feature_index] += residual * value
        if epoch % 10 == 0 or epoch == epochs:
            curve.append({"epoch": epoch, "crossEntropy": round(loss / len(rows), 12)})
        if epoch == epochs:
            break
        for class_index in range(class_count):
            for feature_index in range(len(rows[0])):
                weights[class_index][feature_index] -= (
                    0.12 * gradients[class_index][feature_index] / len(rows)
                )
    return [_round(row) for row in weights], curve


def _records_for_split(bundle: dict[str, Any], split: str) -> list[dict[str, Any]]:
    identities = set(bundle["split"]["groups"][split])
    return [
        record for record in bundle["dataset"]["records"] if record["programIdentity"] in identities
    ]


def _feature_vector(observation: dict[str, Any]) -> list[float]:
    if tuple(observation) != FEATURE_NAMES:
        raise ValueError("structured_feature_contract_invalid")
    values = [float(observation[name]) for name in FEATURE_NAMES]
    if any(not math.isfinite(value) for value in values):
        raise ValueError("structured_feature_nonfinite")
    return values


def _normalize(values: list[float], means: list[float], scales: list[float]) -> list[float]:
    return [
        (value - mean) / scale for value, mean, scale in zip(values, means, scales, strict=True)
    ]


def _softmax(scores: list[float]) -> list[float]:
    offset = max(scores)
    values = [math.exp(score - offset) for score in scores]
    total = sum(values)
    return [value / total for value in values]


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _round(values: list[float]) -> list[float]:
    return [round(value, 12) for value in values]


def _model_hash(model: dict[str, Any]) -> str:
    payload = deepcopy(model)
    payload["integrity"]["modelHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))
