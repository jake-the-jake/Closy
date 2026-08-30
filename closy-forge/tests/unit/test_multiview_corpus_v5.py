from __future__ import annotations

from closy_forge.pattern_inference.multiview_corpus_v5 import (
    FEATURE_NAMES,
    build_multiview_corpus_v5,
    compact_corpus_manifest_v5,
    validate_multiview_corpus_v5,
)


def test_smoke_corpus_uses_3d_zbuffer_and_preserves_view_roles() -> None:
    dataset, split = build_multiview_corpus_v5(
        programs_per_family=4,
        captures_per_program=1,
    )

    assert validate_multiview_corpus_v5(dataset, split) == []
    assert len(dataset["programs"]) == 32
    assert len(dataset["captures"]) == 32
    assert dataset["renderer"]["decodedImageCount"] == 128
    assert dataset["sourceRepresentation"] == "assembled_reference_3d_simulation_mesh"
    assert dataset["physicalSettleClaimed"] is False
    assert dataset["featureContract"]["viewAveragingBeforeModel"] is False
    assert tuple(dataset["captures"][0]["input"]) == FEATURE_NAMES
    assert all(
        item["referenceAudit"]["simulationTriangleCount"] > 0 for item in dataset["programs"]
    )


def test_compact_manifest_excludes_features_pixels_and_program_targets() -> None:
    dataset, split = build_multiview_corpus_v5(
        programs_per_family=4,
        captures_per_program=1,
    )
    manifest = compact_corpus_manifest_v5(dataset, split)

    assert "captures" not in manifest
    assert "target" not in str(manifest["programInventory"])
    assert manifest["rawRastersPersisted"] is False
    assert manifest["counts"]["decodedImages"] == 128
