from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from closy_forge.integrated_runtime.evidence import validate_integrated_runtime_evidence
from closy_forge.package_io.canonical_json import canonical_dumps, read_json
from closy_forge.package_io.hashing import sha256_bytes
from closy_forge.zeroone.invalidation_ledger import (
    validate_integrated_runtime_invalidation_ledger,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/integrated_runtime_avatar_outfit_v2.json"
LEDGER = ROOT / "docs/evidence/integrated_runtime_invalidation_ledger_d0_v1.json"
OUTFIT = ROOT / "docs/evidence/canonical_outfit_surface_d0_v1.json"
REPLAY = ROOT / "docs/evidence/integrated_replay_manifest_d0_v1.json"


def _replay_generator() -> ModuleType:
    path = ROOT / "scripts/generate_integrated_replay_manifest.py"
    spec = importlib.util.spec_from_file_location("integrated_replay_generator", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_integrated_runtime_evidence_is_current_and_truthful() -> None:
    evidence = _object(EVIDENCE)

    assert validate_integrated_runtime_evidence(evidence) == []
    assert evidence["generationSourceSha"] == "dd916913ac14119bc2e127989703f1c51f91e00a"
    assert evidence["packageExecution"]["packageValidityDependsOnZeroOne"] is False
    assert evidence["runtimeDecision"]["staticSource"] == "zeroone_static"
    assert evidence["runtimeDecision"]["motionSource"] == "zeroone_mt1_reference_motion"
    assert evidence["runtimeDecision"]["avatarSource"] == "synthetic_avatar_d0"
    assert evidence["runtimeDecision"]["layerSource"] == "canonical_surface_layer_d0"
    assert evidence["truth"]["blueprintZ2Passed"] is False
    assert evidence["truth"]["phy1Passed"] is False
    assert evidence["truth"]["mobileDevice"] == "not_run"

    integrity = dict(evidence)
    integrity.pop("integrity")
    assert evidence["integrity"]["evidenceHash"] == sha256_bytes(
        canonical_dumps(integrity).encode()
    )


def test_detached_outfit_and_invalidation_records_match_integrated_authority() -> None:
    evidence = _object(EVIDENCE)
    ledger = _object(LEDGER)
    outfit = _object(OUTFIT)

    assert ledger == evidence["invalidationLedger"]
    assert outfit == evidence["outfit"]
    assert (
        validate_integrated_runtime_invalidation_ledger(ledger, ledger["currentIdentities"]) == []
    )
    assert outfit["initial"]["contactCount"] == 32
    assert outfit["final"]["unresolvedContactCount"] == 0
    assert outfit["intersectionAudit"]["initialIntersections"] == 256
    assert outfit["intersectionAudit"]["finalIntersections"] == 0
    assert outfit["surfaceExecution"]["metadataOnly"] is False
    assert outfit["truth"]["physicalSimulation"] is False


def test_replay_manifest_disposes_every_source_and_proves_no_duplicate_business_patch() -> None:
    replay = _object(REPLAY)

    assert replay["baseHead"] == "4c5dcd284a1221a7820184e640fb92b67b880787"
    assert replay["replayEnd"] == "01b03133f0e5479bd1955c570a168aa2fbfbfa1e"
    assert replay["sourceCommitCount"] == 41
    assert len(replay["dispositions"]) == 41
    assert replay["sharedWorkflow"]["replayedCopyCount"] == 0
    assert replay["validation"] == {
        "allAppliedCommitsHaveCherryPickXTrailer": True,
        "allSourceCommitsDisposed": True,
        "mergeCommitUsed": False,
        "pr26BusinessPatchesExactlyOnce": True,
        "pr31BusinessPatchesExactlyOnce": True,
    }
    assert all(
        row["matchingPatchCountInReplay"] == 1 for row in replay["duplicateBusinessPatchProof"]
    )


def test_replay_dispositions_bind_each_source_to_its_own_result_patch() -> None:
    module = _replay_generator()
    sources = ["a" * 40, "b" * 40, "c" * 40]
    results = ["1" * 40, "2" * 40, "3" * 40]
    rows = [
        {
            "sourceSha": source,
            "sourcePatchId": f"patch-{ordinal}",
            "resultSha": result,
            "resultPatchId": f"patch-{ordinal}",
            "cherryPickXVerified": True,
        }
        for ordinal, (source, result) in enumerate(zip(sources, results, strict=True))
    ]
    module._validate_dispositions(rows, sources, {value: i for i, value in enumerate(results)})

    stale_last_result = [dict(row, resultPatchId="patch-2") for row in rows]
    with pytest.raises(ValueError, match="replay_patch_id_mismatch"):
        module._validate_dispositions(
            stale_last_result,
            sources,
            {value: i for i, value in enumerate(results)},
        )


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("missing", "replay_disposition_source_order_invalid"),
        ("duplicate_source", "replay_disposition_source_duplicate"),
        ("duplicate_result", "replay_disposition_result_duplicate"),
        ("reordered", "replay_disposition_source_order_invalid"),
        ("missing_trailer", "replay_cherry_pick_trailer_missing"),
    ],
)
def test_replay_mapping_mutations_fail_closed(mutation: str, error: str) -> None:
    module = _replay_generator()
    sources = ["a" * 40, "b" * 40, "c" * 40]
    results = ["1" * 40, "2" * 40, "3" * 40]
    rows = [
        {
            "sourceSha": source,
            "sourcePatchId": f"patch-{ordinal}",
            "resultSha": result,
            "resultPatchId": f"patch-{ordinal}",
            "cherryPickXVerified": True,
        }
        for ordinal, (source, result) in enumerate(zip(sources, results, strict=True))
    ]
    if mutation == "missing":
        rows.pop()
    elif mutation == "duplicate_source":
        rows[1]["sourceSha"] = rows[0]["sourceSha"]
    elif mutation == "duplicate_result":
        rows[1]["resultSha"] = rows[0]["resultSha"]
    elif mutation == "reordered":
        rows[0], rows[1] = rows[1], rows[0]
    else:
        rows[1]["cherryPickXVerified"] = False
    with pytest.raises(ValueError, match=error):
        module._validate_dispositions(rows, sources, {value: i for i, value in enumerate(results)})


def test_portable_evidence_contains_no_private_or_device_overclaim() -> None:
    serialized = EVIDENCE.read_text(encoding="utf-8").lower()

    for forbidden in (
        "rawsourcesha256",
        "private-source-registry",
        "useridentity",
        "credential",
        "c:\\users\\",
        "/home/",
    ):
        assert forbidden not in serialized


def _object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    assert isinstance(value, dict)
    return value
