from __future__ import annotations

from copy import deepcopy

import pytest

from closy_forge.pattern_inference.typed_program_v2 import (
    CONTINUOUS_AXES,
    GRAMMAR_VERSION,
    PROGRAM_VERSION,
    TOKEN_AXES,
    build_typed_dataset_v2,
    compact_typed_dataset_manifest_v2,
    compile_typed_program_v2,
    legal_token_values,
    validate_typed_dataset_v2,
    validate_typed_program_v2,
)


def _valid_program() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "programVersion": PROGRAM_VERSION,
        "grammarVersion": GRAMMAR_VERSION,
        "programId": "typed.test.valid",
        "tokens": dict(
            zip(
                TOKEN_AXES,
                (
                    "upper",
                    "split_front",
                    "none",
                    "long",
                    "collar",
                    "shaped",
                    "straight",
                    "front_placket",
                    "base",
                    "woven",
                ),
                strict=True,
            )
        ),
        "parameters": dict(zip(CONTINUOUS_AXES, (0.55, 0.6, 0.3, 0.8, 0.2), strict=True)),
        "materialRegion": "material.woven",
    }


def test_typed_program_compiles_real_panels_seams_openings_and_reference_mesh() -> None:
    program = _valid_program()

    compilation = compile_typed_program_v2(program)

    assert validate_typed_program_v2(program) == []
    assert compilation["audit"]["topologyValid"] is True
    assert compilation["audit"]["physicalSettleClaimed"] is False
    assert compilation["audit"]["meshTriangleCount"] > 0
    assert compilation["audit"]["panelCount"] == len(compilation["panels"])
    assert compilation["seams"]
    assert compilation["openings"]
    assert all(row["leftLength"] > 0.0 for row in compilation["audit"]["seamLengths"])
    assert all(row["rightLength"] > 0.0 for row in compilation["audit"]["seamLengths"])


def test_typed_grammar_rejects_illegal_and_corrupt_programs_fail_closed() -> None:
    program = _valid_program()
    corrupt = deepcopy(program)
    corrupt["tokens"]["base"] = "lower"  # type: ignore[index]

    issues = validate_typed_program_v2(corrupt)

    assert "typed_token_illegal:torso:split_front" in issues
    assert "typed_token_illegal:sleeve:long" in issues
    assert "typed_token_illegal:neckline:collar" in issues
    with pytest.raises(ValueError, match="typed_program_invalid"):
        compile_typed_program_v2(corrupt)
    assert legal_token_values({"base": "lower"}, "torso") == ("none",)


def test_typed_dataset_has_exact_compositional_split_and_compact_manifest() -> None:
    dataset = build_typed_dataset_v2()
    manifest = compact_typed_dataset_manifest_v2(dataset)

    assert validate_typed_dataset_v2(dataset) == []
    assert dataset["split"]["counts"] == {"train": 256, "validation": 64, "test": 96}
    assert {
        record["target"]["compilation"]["audit"]["panelCount"] for record in dataset["records"]
    } == {7, 8, 9, 10, 11}
    assert all(
        item["testCount"] == 24
        and item["exactCombinationPresentInTraining"] is False
        and item["atomsPresentInTraining"] is True
        for item in dataset["split"]["heldoutStructuralCompositionGroups"]
    )
    assert manifest["rawRastersPersisted"] is False
    assert "records" not in manifest
    assert len(manifest["manifestHash"]) == 64
