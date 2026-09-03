from __future__ import annotations

from pathlib import Path

from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs" / "evidence" / "d0_v4_engineering"


def _assert_digest(value: dict[str, object]) -> None:
    claimed = value["resultDigest"]
    value["resultDigest"] = ""
    assert claimed == sha256_bytes(canonical_dumps(value).encode("utf-8"))


def test_publication_cards_reconcile_without_reading_public_test_targets() -> None:
    data = read_json(EVIDENCE / "data_card.json")
    model = read_json(EVIDENCE / "model_card.json")
    trials = read_json(EVIDENCE / "trial_inventory.json")
    readiness = read_json(EVIDENCE / "development_readiness.json")
    inventory = read_json(EVIDENCE / "source_inventory.json")
    for value in (data, model, trials, readiness, inventory):
        _assert_digest(value)
    assert data["developmentPartitionCounts"] == {"train": 512, "validation": 128}
    assert data["guardedPublicTestCount"] == 128
    assert data["publicTestTargetsReadWhileBuildingCard"] is False
    assert model["targetCount"] == 11
    assert model["targetParametersReadAtInference"] is False
    assert trials["consumed"] == 6
    assert readiness["readinessPass"] is True
    assert readiness["createsQualificationCohort"] is False
    assert inventory["publicTestTargetsRead"] is False
    assert all("public_test" not in item["path"] for item in inventory["files"])


def test_representative_atlas_has_lineage_and_distinct_novel_views() -> None:
    evidence = read_json(EVIDENCE / "appearance" / "representative_091" / "evidence.json")
    _assert_digest(evidence)
    assert evidence["novelViewsDifferFromFront"] is True
    assert evidence["lineageIsPanelUvNotCameraPlane"] is True
    assert evidence["physicalMaterialAccuracyClaimed"] is False
    for path in evidence["artifacts"].values():
        assert (ROOT / path).is_file()
