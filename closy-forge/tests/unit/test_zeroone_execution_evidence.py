from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

EVIDENCE = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "evidence"
    / "phase10_zeroone_static"
    / "execution_evidence.json"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FAMILIES = {
    "tshirt",
    "sleeveless_top",
    "long_sleeved_top",
    "simple_skirt",
    "simple_trousers",
    "simple_dress",
    "button_shirt",
    "jacket_outerwear",
    "layered_asymmetric",
}


def test_committed_zeroone_evidence_proves_all_family_execution_truth() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert evidence["schemaVersion"] == "closy.zeroone.execution-evidence.v2"
    assert evidence["scope"] == "candidate_branch_local_cpu_static_all_predeclared_families"
    assert evidence["axes"] == {
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic",
        "executionProfile": "CPU",
        "gateScope": "static ZeroOne",
    }
    assert evidence["closy"]["gitSha"] == "9d7026b7b98c0122c36f8a1c5aa48a1b4a196dd5"
    assert evidence["closy"]["contentDirty"] is False
    assert evidence["zeroOne"]["gitSha"] == "13a844d240f4bbb2cafde105c4a0bdca8d89a06b"
    assert evidence["zeroOne"]["sourceClassification"] == ("unmerged_candidate_static_pr_head")
    assert evidence["zeroOne"]["contentDirty"] is False
    assert evidence["tool"]["zeroOneGitSha"] == evidence["zeroOne"]["gitSha"]
    assert evidence["tool"]["executableSha256"] == evidence["executableSha256"]
    assert evidence["trustedBuildRecord"]["executableSha256"] == evidence["executableSha256"]
    assert evidence["trustedBuildRecord"]["sourceSha"] == evidence["zeroOne"]["gitSha"]
    assert evidence["trustedBuildRecord"]["attestation"]["available"] is True
    assert evidence["zeroOneWorkflowEvidence"]["runId"] == 33187775880
    assert evidence["zeroOneWorkflowEvidence"]["artifactId"] == 9692554312
    assert evidence["timings"]["wallNanoseconds"] > 0
    assert evidence["timings"]["cpuNanoseconds"] > 0

    rows = {row["family"]: row for row in evidence["garments"]}
    assert set(rows) == FAMILIES
    for row in rows.values():
        integration = row["integration"]
        assert SHA256_RE.fullmatch(row["canonicalPackageDigest"])
        assert integration["contractVersion"] == "closy.zeroone.integration-result.v2"
        assert integration["fallbackPreserved"] is True
        assert integration["canonicalAuthorityPreserved"] is True
        assert integration["actualZeroOneDynamicDeformationExecuted"] is False
        assert integration["actualZeroOneGpuRuntimeExecuted"] is False
        assert integration["actualZeroOneMobileRuntimeExecuted"] is False
        assert row["familyInventory"]["semanticBoundaryPreservation"] is True
        assert SHA256_RE.fullmatch(row["familyInventory"]["topologyHash"])
        _assert_valid_family(row)

    acceptance = evidence["acceptance"]
    assert acceptance["allPredeclaredFamiliesExecuted"] is True
    assert acceptance["allCanonicalAuthoritiesPreserved"] is True
    assert acceptance["allFallbacksPreserved"] is True
    assert acceptance["actualZeroOneStaticCookExecutedThisInvocation"] is True
    assert acceptance["actualZeroOneStaticArtifactLoaded"] is True
    assert acceptance["cacheValidated"] is True
    assert acceptance["allDerivativesDeterministic"] is True
    assert acceptance["allNamespacesValid"] is True
    assert acceptance["allIndependentDerivativeInspectionsPassed"] is True
    assert acceptance["allDeleteAndRebuildProofsPassed"] is True
    assert acceptance["scopedCandidateBranchGateZ1Passed"] is True
    assert acceptance["currentMasterGateZ1Passed"] is False
    assert acceptance["globalPhase10Complete"] is False
    assert evidence["evidenceClassification"]["scopedCandidateStaticPass"] is True


def _assert_valid_family(row: dict[str, Any]) -> None:
    integration = row["integration"]
    report = integration["report"]
    assert integration["status"] == "valid"
    assert integration["actualZeroOneStaticCookExecutedThisInvocation"] is True
    assert integration["actualZeroOneStaticArtifactLoaded"] is True
    assert integration["cacheValidated"] is True
    assert integration["deterministicDerivative"] is True
    assert report["canonicalPackageBytesUnchanged"] is True
    assert report["cleanRunA"]["cacheState"] == "miss"
    assert report["cacheHitRun"]["cacheState"] == "hit"
    assert report["resumeRun"]["interruptionDiagnostic"] == (
        "E_INJECTED_INTERRUPTION_BEFORE_PUBLICATION"
    )
    assert report["resumeRun"]["resumeState"] == "matched"
    assert report["resumeRun"]["validatedNativeDerivative"] is True
    assert report["resumeRun"]["canonicalDerivativeHash"] == report["canonicalDerivativeHash"]
    assert report["cleanRunB"]["cacheState"] == "miss"
    assert row["namespaceAudit"]["status"] == "derivative_valid"
    assert row["independentDerivativeInspection"]["status"] == "pass"
    rebuild = row["deleteAndRebuild"]
    assert rebuild["executed"] is True
    assert rebuild["passed"] is True
    assert rebuild["canonicalDerivativeHashBefore"] == rebuild["canonicalDerivativeHashAfter"]
