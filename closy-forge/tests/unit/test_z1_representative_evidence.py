from __future__ import annotations

import json
from pathlib import Path

EVIDENCE_ROOT = Path(__file__).resolve().parents[2] / "docs/evidence/phase10_zeroone_static"


def test_representative_static_profile_is_frozen_and_passes() -> None:
    manifest = json.loads(
        (EVIDENCE_ROOT / "z1_representative_manifest.json").read_text(encoding="utf-8")
    )
    evidence = json.loads(
        (EVIDENCE_ROOT / "z1_representative_evidence.json").read_text(encoding="utf-8")
    )

    assert manifest["profileId"] == "Z1-D0-representative-static"
    assert manifest["frozenBeforeExecution"] is True
    assert manifest["family"] == evidence["family"] == "tshirt"
    assert manifest["canonicalPackageDigest"] == evidence["canonicalPackageDigest"]
    assert manifest["pairedC3Binding"]["capabilityId"] == "C3-Binding-D0"
    assert manifest["pairedC3Binding"]["acceptedForD0RuntimeBindingProfile"] is True
    assert evidence["status"] == "pass"
    assert evidence["frozenManifest"]["unchangedAfterExecution"] is True
    assert evidence["integration"]["status"] == "valid"
    assert evidence["integration"]["report"]["resumeRun"]["resumeState"] == "matched"
    assert evidence["namespaceAudit"]["status"] == "derivative_valid"
    assert evidence["independentDerivativeInspection"]["status"] == "pass"
    assert evidence["deleteAndRebuild"]["passed"] is True
    assert evidence["claims"]["representativeStaticProfilePassed"] is True
    assert evidence["claims"]["currentMasterZ1Passed"] is False
    assert evidence["claims"]["globalZ1Passed"] is False
