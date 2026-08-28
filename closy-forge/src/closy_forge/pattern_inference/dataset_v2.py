from __future__ import annotations

import random
from copy import deepcopy
from typing import Any

from .grammar_v2 import FAMILY_SPECS, default_parameters, program_from_parameters

DATASET_VERSION_V2 = "closy.synthetic_pattern_dataset.d0.v2"
SPLIT_VERSION_V2 = "closy.pattern_dataset_split.d0.v2"
FEATURE_NAMES: tuple[str, ...] = (
    "maskAspectRatio",
    "upperSilhouetteCoverage",
    "lowerSilhouetteCoverage",
    "lateralReachRatio",
    "hemSpreadRatio",
    "legSeparationResponse",
    "centerEdgeResponse",
    "layerEdgeResponse",
    "bilateralSymmetry",
    "contourComplexity",
    "fabricDrapeResponse",
    "cameraYawNormalized",
    "cameraPitchNormalized",
    "maskNoiseFraction",
    "landmarkNoiseNormalized",
    "occlusionFraction",
    "colourLuma",
    "textureFrequency",
)

FORBIDDEN_INPUT_TOKENS = (
    "family",
    "category",
    "template",
    "panel",
    "opening",
    "target",
    "parameter",
)

_PROTOTYPES: dict[str, tuple[float, ...]] = {
    "sleeveless_top": (1.02, 0.88, 0.08, 0.38, 0.44, 0.02, 0.08, 0.08, 0.98, 0.28, 0.58),
    "long_sleeved_top": (0.96, 0.90, 0.06, 0.92, 0.42, 0.02, 0.08, 0.10, 0.98, 0.44, 0.62),
    "simple_skirt": (1.28, 0.04, 0.92, 0.34, 0.78, 0.03, 0.06, 0.08, 0.98, 0.34, 0.72),
    "simple_trousers": (1.78, 0.04, 0.94, 0.31, 0.30, 0.84, 0.08, 0.09, 0.97, 0.54, 0.52),
    "simple_dress": (1.72, 0.70, 0.88, 0.42, 0.74, 0.04, 0.10, 0.12, 0.97, 0.48, 0.76),
    "button_shirt": (1.06, 0.93, 0.07, 0.90, 0.46, 0.02, 0.92, 0.18, 0.98, 0.68, 0.42),
    "jacket_outerwear": (1.10, 0.96, 0.09, 0.94, 0.52, 0.02, 0.72, 0.62, 0.96, 0.76, 0.36),
    "layered_asymmetric": (1.14, 0.91, 0.12, 0.40, 0.72, 0.03, 0.12, 0.96, 0.64, 0.82, 0.82),
}


def build_synthetic_dataset_v2(
    *, seed: int = 2901, groups_per_family: int = 12, observations_per_group: int = 4
) -> tuple[dict[str, Any], dict[str, Any]]:
    if groups_per_family < 12 or observations_per_group < 4:
        raise ValueError("learned_d0_dataset_requires_at_least_12_groups_and_4_observations")
    samples: list[dict[str, Any]] = []
    programs: dict[str, dict[str, Any]] = {}
    split_groups: dict[str, list[str]] = {"train": [], "validation": [], "test": []}
    for family_index, family in enumerate(FAMILY_SPECS):
        for group_index in range(groups_per_family):
            group_id = f"program.{family}.{group_index:03d}"
            group_seed = seed + family_index * 10_000 + group_index * 101
            length_delta, width_delta, ease_delta = _program_deltas(group_index)
            parameters = _varied_parameters(family, length_delta, width_delta, ease_delta)
            corrections = _correction_operations(family, group_index, parameters)
            programs[group_id] = program_from_parameters(
                family,
                parameters,
                program_id=group_id,
                base_seed=group_seed,
                corrections=corrections,
            )
            split_name = _group_split(group_index, groups_per_family)
            split_groups[split_name].append(group_id)
            for observation_index in range(observations_per_group):
                observation_seed = group_seed + observation_index
                observation = _capture_observation(
                    family,
                    length_delta=length_delta,
                    width_delta=width_delta,
                    ease_delta=ease_delta,
                    observation_index=observation_index,
                    seed=observation_seed,
                )
                samples.append(
                    {
                        "sampleId": f"capture.{family}.{group_index:03d}.{observation_index:02d}",
                        "programGroupId": group_id,
                        "observationSeed": observation_seed,
                        "sourceKind": "project_authored_synthetic_capture",
                        "input": observation,
                        "target": {
                            "garmentFamily": family,
                            "programId": group_id,
                            "continuousParameters": {
                                "lengthScale": round(1.0 + length_delta, 9),
                                "widthScale": round(1.0 + width_delta, 9),
                                "easeNormalized": round(ease_delta / 0.012, 9),
                            },
                            "materialPresetId": _material_variant(group_index),
                        },
                        "containsPrivateData": False,
                    }
                )
    challenge_set = _challenge_set(seed + 900_000)
    dataset = {
        "schemaVersion": 1,
        "datasetVersion": DATASET_VERSION_V2,
        "seed": seed,
        "generator": "closy.pattern_inference.synthetic_capture_generator.d0.v2",
        "featureNames": list(FEATURE_NAMES),
        "programs": [programs[key] for key in sorted(programs)],
        "samples": samples,
        "challengeSet": challenge_set,
        "containsPrivateData": False,
        "licence": "project-authored; internal Closy test and development use",
    }
    split = {
        "schemaVersion": 1,
        "splitVersion": SPLIT_VERSION_V2,
        "groupKey": "programGroupId",
        "splitPolicy": (
            "within_each_family_program_groups_0_to_7_train_" "8_to_9_validation_10_plus_test"
        ),
        "groups": {name: sorted(values) for name, values in split_groups.items()},
        "samples": {
            name: [
                sample["sampleId"]
                for sample in samples
                if sample["programGroupId"] in set(split_groups[name])
            ]
            for name in ("train", "validation", "test")
        },
    }
    issues = validate_dataset_v2(dataset, split)
    if issues:
        raise ValueError("invalid_synthetic_dataset_v2:" + ";".join(issues))
    return dataset, split


def validate_dataset_v2(dataset: dict[str, Any], split: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    samples = dataset.get("samples", [])
    programs = dataset.get("programs", [])
    sample_ids = [str(sample.get("sampleId")) for sample in samples]
    program_ids = [str(program.get("programId")) for program in programs]
    if dataset.get("datasetVersion") != DATASET_VERSION_V2:
        issues.append("dataset_version_invalid")
    if len(samples) < 384 or len(programs) < 96:
        issues.append("dataset_scale_insufficient")
    if len(sample_ids) != len(set(sample_ids)) or len(program_ids) != len(set(program_ids)):
        issues.append("dataset_identity_duplicate")
    if tuple(dataset.get("featureNames", [])) != FEATURE_NAMES:
        issues.append("dataset_feature_contract_invalid")
    for sample in samples:
        observation = sample.get("input", {})
        if tuple(observation) != FEATURE_NAMES:
            issues.append("capture_feature_set_invalid")
        if _contains_forbidden_input_key(observation):
            issues.append("adversarial_feature_leakage_detected")
        values = list(observation.values())
        if any(isinstance(value, bool) or not isinstance(value, int | float) for value in values):
            issues.append("capture_feature_non_numeric")

    split_group_sets = {
        name: set(map(str, split.get("groups", {}).get(name, [])))
        for name in ("train", "validation", "test")
    }
    if any(not values for values in split_group_sets.values()):
        issues.append("dataset_split_empty")
    if any(
        split_group_sets[left] & split_group_sets[right]
        for left, right in (
            ("train", "validation"),
            ("train", "test"),
            ("validation", "test"),
        )
    ):
        issues.append("program_identity_leakage")
    if set().union(*split_group_sets.values()) != set(program_ids):
        issues.append("dataset_split_program_coverage_invalid")
    sample_groups = {
        str(sample.get("sampleId")): str(sample.get("programGroupId")) for sample in samples
    }
    for name, groups in split_group_sets.items():
        declared_samples = set(map(str, split.get("samples", {}).get(name, [])))
        recomputed_samples = {
            sample_id for sample_id, group_id in sample_groups.items() if group_id in groups
        }
        if declared_samples != recomputed_samples:
            issues.append("dataset_split_sample_membership_invalid")
    challenge_kinds = {str(item.get("kind")) for item in dataset.get("challengeSet", [])}
    if challenge_kinds != {"ambiguous", "negative", "unsupported", "corrupted"}:
        issues.append("challenge_set_incomplete")
    return sorted(set(issues))


def samples_for_split(
    dataset: dict[str, Any], split: dict[str, Any], split_name: str
) -> list[dict[str, Any]]:
    ids = set(split["samples"][split_name])
    return [sample for sample in dataset["samples"] if sample["sampleId"] in ids]


def feature_vector(observation: dict[str, Any]) -> list[float]:
    return [float(observation[name]) for name in FEATURE_NAMES]


def _program_deltas(group_index: int) -> tuple[float, float, float]:
    length_steps = (-0.10, -0.06, -0.03, 0.0, 0.03, 0.06, 0.10)
    width_steps = (-0.07, -0.035, 0.0, 0.035, 0.07)
    ease_steps = (-0.010, -0.005, 0.0, 0.005, 0.010)
    return (
        length_steps[group_index % len(length_steps)],
        width_steps[(group_index * 2 + 1) % len(width_steps)],
        ease_steps[(group_index * 3 + 2) % len(ease_steps)],
    )


def _varied_parameters(
    family: str, length_delta: float, width_delta: float, ease_delta: float
) -> dict[str, float | int]:
    spec = FAMILY_SPECS[family]
    values = default_parameters(family)
    values[spec.length_field] = round(float(values[spec.length_field]) * (1.0 + length_delta), 9)
    values[spec.width_field] = round(float(values[spec.width_field]) * (1.0 + width_delta), 9)
    values[spec.ease_field] = round(float(values[spec.ease_field]) + ease_delta, 9)
    params = spec.parameter_type(**values)
    params.validate()
    return dict(params.to_json())


def _capture_observation(
    family: str,
    *,
    length_delta: float,
    width_delta: float,
    ease_delta: float,
    observation_index: int,
    seed: int,
) -> dict[str, float]:
    rng = random.Random(seed)
    prototype = list(_PROTOTYPES[family])
    prototype[0] += length_delta * 0.72 - width_delta * 0.28
    prototype[1] += width_delta * 0.32
    prototype[2] += width_delta * 0.28
    prototype[4] += width_delta * 0.40
    prototype[10] += ease_delta * 4.0
    noise = 0.006 + observation_index * 0.004
    capture = [value + rng.uniform(-noise, noise) for value in prototype]
    camera_yaw = (-0.24, -0.08, 0.09, 0.22)[observation_index % 4]
    camera_pitch = (-0.08, 0.03, 0.08, -0.02)[observation_index % 4]
    mask_noise = (0.0, 0.012, 0.025, 0.04)[observation_index % 4]
    landmark_noise = (0.0, 0.018, 0.032, 0.05)[observation_index % 4]
    occlusion = (0.0, 0.03, 0.08, 0.14)[observation_index % 4]
    colour_luma = 0.35 + ((seed % 17) / 40.0)
    texture_frequency = 0.15 + ((seed % 13) / 24.0)
    values = capture + [
        camera_yaw,
        camera_pitch,
        mask_noise,
        landmark_noise,
        occlusion,
        colour_luma,
        texture_frequency,
    ]
    return {name: round(value, 9) for name, value in zip(FEATURE_NAMES, values, strict=True)}


def _challenge_set(seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    records: list[dict[str, Any]] = []
    families = list(FAMILY_SPECS)
    for index in range(8):
        left = families[index]
        right = families[(index + 1) % len(families)]
        blended = [
            (a + b) / 2 + rng.uniform(-0.01, 0.01)
            for a, b in zip(_PROTOTYPES[left], _PROTOTYPES[right], strict=True)
        ]
        common_tail = [0.0, 0.0, 0.03, 0.04, 0.16, 0.5, 0.5]
        records.append(_challenge("ambiguous", index, blended + common_tail, "defer"))
        records.append(_challenge("negative", index, [0.0] * len(FEATURE_NAMES), "defer"))
        unsupported = [2.8, 1.4, 1.4, 1.5, 1.5, 1.4, 1.4, 1.4, 0.2, 1.8, 1.5] + common_tail
        records.append(_challenge("unsupported", index, unsupported, "defer"))
        corrupted: list[Any] = deepcopy(unsupported)
        corrupted[index % len(corrupted)] = "not-a-number"
        records.append(_challenge("corrupted", index, corrupted, "reject"))
    return records


def _challenge(kind: str, index: int, values: list[Any], action: str) -> dict[str, Any]:
    return {
        "challengeId": f"challenge.{kind}.{index:02d}",
        "kind": kind,
        "input": {name: value for name, value in zip(FEATURE_NAMES, values, strict=True)},
        "expectedAction": action,
        "containsPrivateData": False,
    }


def _group_split(group_index: int, groups_per_family: int) -> str:
    validation_start = groups_per_family - 4
    test_start = groups_per_family - 2
    if group_index >= test_start:
        return "test"
    if group_index >= validation_start:
        return "validation"
    return "train"


def _correction_operations(
    family: str, group_index: int, parameters: dict[str, float | int]
) -> list[dict[str, Any]]:
    if group_index % 5:
        return []
    field = FAMILY_SPECS[family].ease_field
    return [
        {
            "operationId": f"correction.{family}.{group_index:03d}.ease",
            "operation": "set_measurement",
            "field": field,
            "after": parameters[field],
            "source": "simulated_fixture",
            "accepted": True,
            "humanReviewStatus": "not_run",
        }
    ]


def _material_variant(group_index: int) -> str:
    return (
        "material.cotton_jersey_reference_v1",
        "material.lightweight_woven_reference_v1",
        "material.heavy_jersey_reference_v1",
    )[group_index % 3]


def _contains_forbidden_input_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            any(token in str(key).lower() for token in FORBIDDEN_INPUT_TOKENS)
            or _contains_forbidden_input_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_input_key(item) for item in value)
    return False
