from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import canonical_dumps

EVIDENCE = Path(__file__).resolve().parents[2] / "docs" / "evidence"
REFERENCE = EVIDENCE / "phase11_reference_motion_v2"


def test_mt1_evidence_is_complete_and_does_not_promote_z2() -> None:
    execution = _object(REFERENCE / "execution_evidence.json")
    oracle = _object(REFERENCE / "mt1_oracle_report.json")
    static = _object(REFERENCE / "mt1_static_execution.json")
    ledger = _object(REFERENCE / "representation_invalidation_ledger.json")

    assert execution["outcome"] == "scoped_mt1_pass"
    assert execution["dynamic"]["namespaceAdmitted"] is True
    assert execution["dynamic"]["outputIntersectionMaximum"] == 0
    assert execution["dynamic"]["independentIntersectionMaximum"] == 0
    assert execution["claims"] == {
        "blueprintZ2Passed": False,
        "mechanicalTransportReferencePassed": True,
        "phy1Passed": False,
        "physicalTruth": False,
        "productDynamicReadiness": False,
        "solverDrivenClothPassed": False,
    }
    assert execution["applicability"]["Phase11"] == "partial"
    assert execution["applicability"]["globalZ2"] == "partial"
    assert all(oracle["checks"].values())
    assert oracle["maximumPositionErrorMetres"] <= 2.0e-6
    assert oracle["p95PositionErrorMetres"] <= 5.0e-7
    assert oracle["maximumBoundaryCrackMeters"] <= 5.0e-5
    assert oracle["maximumOpeningLoopDistanceMeters"] <= 5.0e-5
    assert static["assetAudit"]["triangleCount"] == 832
    assert static["assetAudit"]["vertexCount"] == 2496
    assert static["canonicalAuthorityPreserved"] is True
    assert ledger["calculatedInvalidation"]["notInvalidated"] == [
        "canonical_package_identity",
        "fallback_runtime",
    ]
    assert not _contains_private_path(execution)


def test_representation_localization_preserves_historical_and_v2_truth() -> None:
    report = _object(REFERENCE / "representation_localization.json")
    integrity = report.pop("integrity")
    expected = hashlib.sha256(canonical_dumps(report).encode("utf-8")).hexdigest()
    representations = {row["representationId"]: row for row in report["representations"]}

    assert integrity["manifestHash"] == expected
    assert report["localization"]["firstInvalidTransformation"] == ("logical_fallback_render_mesh")
    assert representations["canonical_stitched_simulation_rest"]["intersectingPairCount"] == 0
    assert representations["logical_fallback_render_mesh"]["intersectingPairCount"] > 0
    assert representations["dynamic_processing_surface_before_zeroone"]["intersectingPairCount"] > 0
    assert report["historicalV1IntersectionCountByFrame"] == [
        971,
        931,
        930,
        931,
        929,
        933,
        933,
        933,
        929,
        931,
        930,
        931,
        971,
    ]
    assert report["historicalCorrection"]["sourceFileMutated"] is False


def _contains_private_path(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_private_path(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_private_path(item) for item in value)
    if not isinstance(value, str):
        return False
    folded = value.replace("\\", "/").casefold()
    drive_path = re.match(r"^[a-z]:/", folded) is not None
    return drive_path or folded.startswith("/") or "/users/" in folded


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value
