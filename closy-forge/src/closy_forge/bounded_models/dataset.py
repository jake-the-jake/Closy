from __future__ import annotations

from copy import deepcopy
from random import Random
from typing import Any

from closy_forge.simulation.material_physics import build_material_preset_registry

from .contracts import (
    DATASET_VERSION,
    FAILURE_TARGETS,
    canonical_hash,
    rounded,
    validate_feature_snapshot,
)
from .solver_fixtures import run_project_authored_settle_fixture

DATASET_SEED = 140031
SPLIT_SCENARIO_COUNTS = {"train": 60, "validation": 18, "test": 18}


def build_phase14_dataset(*, seed: int = DATASET_SEED) -> dict[str, Any]:
    presets = build_material_preset_registry()["presets"]
    rows: list[dict[str, Any]] = []
    split_groups: dict[str, dict[str, list[str]]] = {}
    for split_index, (split_name, count) in enumerate(SPLIT_SCENARIO_COUNTS.items()):
        rng = Random(seed + split_index * 1009)
        groups = _group_inventory(split_name)
        split_groups[split_name] = groups
        for scenario_index in range(count):
            scenario = _scenario_features(rng, scenario_index)
            source_group = groups["sourceGroups"][scenario_index % len(groups["sourceGroups"])]
            program_group = groups["programGroups"][
                (scenario_index * 3) % len(groups["programGroups"])
            ]
            avatar_group = groups["avatarGroups"][
                (scenario_index * 5) % len(groups["avatarGroups"])
            ]
            scenario_id = f"scenario.{split_name}.{scenario_index:03d}"
            for descriptor in presets:
                preset_id = str(descriptor["presetId"])
                features = {**scenario, **_material_features(descriptor)}
                issues = validate_feature_snapshot(features)
                if issues:
                    raise RuntimeError(issues[0])
                frozen = deepcopy(features)
                snapshot_hash = canonical_hash(frozen)
                outcome = run_project_authored_settle_fixture(frozen)
                if canonical_hash(frozen) != snapshot_hash:
                    raise RuntimeError("feature_snapshot_mutated_during_solver_execution")
                rows.append(
                    {
                        "rowId": f"{scenario_id}.{preset_id}",
                        "split": split_name,
                        "sourceGroup": source_group,
                        "programGroup": program_group,
                        "avatarGroup": avatar_group,
                        "scenarioId": scenario_id,
                        "presetId": preset_id,
                        "featureSnapshot": frozen,
                        "featureSnapshotHash": snapshot_hash,
                        "solverOutcome": outcome,
                        "targets": {
                            "materialQualityScore": outcome["materialQualityScore"],
                            "failures": {
                                name: outcome["failureLabels"][name] for name in FAILURE_TARGETS
                            },
                        },
                    }
                )
    manifest = {
        "splitPolicy": "source_program_avatar_group_disjoint",
        "groups": split_groups,
        "intersections": _split_intersections(split_groups),
        "trainOnlyPreprocessingRequired": True,
    }
    dataset: dict[str, Any] = {
        "schemaVersion": 1,
        "datasetVersion": DATASET_VERSION,
        "seed": seed,
        "fixtureKind": "project_authored_public_numerical_solver_outcomes",
        "externalDataUsed": False,
        "privateUserDataUsed": False,
        "licensedThirdPartyDataUsed": False,
        "scenarioCounts": dict(SPLIT_SCENARIO_COUNTS),
        "candidatePresetCount": len(presets),
        "rowCount": len(rows),
        "splitManifest": manifest,
        "rows": rows,
        "integrity": {"datasetHash": ""},
    }
    dataset["integrity"]["datasetHash"] = dataset_hash(dataset)
    return dataset


def dataset_hash(dataset: dict[str, Any]) -> str:
    payload = deepcopy(dataset)
    payload.setdefault("integrity", {})["datasetHash"] = ""
    return canonical_hash(payload)


def rows_for_split(dataset: dict[str, Any], split: str) -> list[dict[str, Any]]:
    return [row for row in dataset["rows"] if row["split"] == split]


def validate_split_manifest(dataset: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    manifest = dataset.get("splitManifest", {})
    intersections = manifest.get("intersections", {})
    if any(intersections.get(axis) for axis in ("sourceGroups", "programGroups", "avatarGroups")):
        issues.append("group_split_leakage")
    for row in dataset.get("rows", []):
        if canonical_hash(row.get("featureSnapshot")) != row.get("featureSnapshotHash"):
            issues.append("feature_snapshot_hash_mismatch")
        issues.extend(validate_feature_snapshot(row.get("featureSnapshot", {})))
    if dataset.get("integrity", {}).get("datasetHash") != dataset_hash(dataset):
        issues.append("dataset_hash_mismatch")
    return sorted(set(issues))


def _group_inventory(split: str) -> dict[str, list[str]]:
    count = 8 if split == "train" else 4
    return {
        "sourceGroups": [f"source.{split}.{index}" for index in range(count)],
        "programGroups": [f"program.{split}.{index}" for index in range(count)],
        "avatarGroups": [f"avatar.{split}.{index}" for index in range(count)],
    }


def _split_intersections(groups: dict[str, dict[str, list[str]]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for axis in ("sourceGroups", "programGroups", "avatarGroups"):
        train = set(groups["train"][axis])
        validation = set(groups["validation"][axis])
        test = set(groups["test"][axis])
        result[axis] = sorted((train & validation) | (train & test) | (validation & test))
    return result


def _scenario_features(rng: Random, index: int) -> dict[str, float]:
    difficulty = (index % 12) / 11.0
    capture = 0.42 + 0.18 * rng.random() if index % 7 == 0 else 0.66 + 0.33 * rng.random()
    return {
        "programPanelComplexity": rounded(0.12 + 0.80 * difficulty),
        "programOpeningRatio": rounded(0.50 + 0.48 * rng.random()),
        "programSeamDensity": rounded(0.15 + 0.78 * ((index * 7) % 13) / 12.0),
        "avatarShoulderRatio": rounded(0.84 + 0.30 * rng.random()),
        "avatarHipRatio": rounded(0.85 + 0.30 * rng.random()),
        "motionAmplitude": rounded(0.05 + 1.25 * ((index * 11) % 17) / 16.0),
        "captureQuality": rounded(capture),
        "initialPenetrationMeters": rounded(0.0002 + 0.018 * difficulty),
    }


def _material_features(descriptor: dict[str, Any]) -> dict[str, float]:
    fields = descriptor["fields"]
    return {
        "materialWarpStiffnessNPerM": float(fields["warpStretchStiffness"]["value"]),
        "materialWeftStiffnessNPerM": float(fields["weftStretchStiffness"]["value"]),
        "materialShearStiffnessNPerM": float(fields["shearStiffness"]["value"]),
        "materialBendStiffnessNm": float(fields["bendStiffness"]["value"]),
        "materialDampingRatio": float(fields["dampingRatio"]["value"]),
        "materialThicknessMeters": float(fields["thickness"]["value"]),
        "materialCollisionClearanceMeters": float(fields["collisionClearance"]["value"]),
        "materialArealDensityKgM2": float(fields["arealDensity"]["value"]),
    }
