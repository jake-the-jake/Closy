from __future__ import annotations

import json
import re
from pathlib import Path

EVIDENCE = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "evidence"
    / "phase10_zeroone_static"
    / "execution_evidence.json"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def test_committed_zeroone_evidence_proves_exact_scoped_execution() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert evidence["schemaVersion"] == "closy.zeroone.execution-evidence.v2"
    assert evidence["scope"] == "historical_local_cpu_static_tshirt_and_layered_asymmetric"
    assert evidence["axes"] == {
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic",
        "executionProfile": "CPU",
        "gateScope": "static ZeroOne",
    }
    assert evidence["evidenceClassification"] == {
        "currentMasterRequalified": False,
        "durableWorkflowArtifact": False,
        "globalZ1Pass": False,
        "historicalLocalPass": True,
    }
    assert evidence["closy"]["gitSha"] == "13c3d281843750c7bcd9db50e309ed129066e9fe"
    assert evidence["closy"]["contentDirty"] is False
    assert evidence["zeroOne"]["gitSha"] == "c6388cbbf53ba8a47831ec25e83808e1edf32194"
    assert evidence["zeroOne"]["contentDirty"] is False
    assert evidence["tool"]["zeroOneGitSha"] == evidence["zeroOne"]["gitSha"]
    assert evidence["tool"]["executableSha256"] == evidence["executableSha256"]
    assert evidence["tool"]["buildConfiguration"] == "Release"
    assert evidence["tool"]["headless"] is True
    assert evidence["tool"]["cpuOnly"] is True
    assert evidence["trustedBuildRecord"]["executableSha256"] == evidence["executableSha256"]
    assert evidence["trustedBuildRecord"]["sourceSha"] == evidence["zeroOne"]["gitSha"]
    assert evidence["trustedBuildRecord"]["attestation"]["available"] is False
    assert evidence["currentZeroOneMasterAnchor"] == ("a17762bc1fc12fbd33f0488634635a5dcfdf8da3")
    assert evidence["timings"]["wallNanoseconds"] > 0
    assert evidence["timings"]["cpuNanoseconds"] > 0

    rows = {row["family"]: row for row in evidence["garments"]}
    assert set(rows) == {"tshirt", "layered_asymmetric"}
    for row in rows.values():
        integration = row["integration"]
        report = integration["report"]
        assert SHA256_RE.fullmatch(row["canonicalPackageDigest"])
        assert integration["schemaVersion"] == 2
        assert integration["contractVersion"] == "closy.zeroone.integration-result.v2"
        assert integration["status"] == "valid"
        assert integration["actualZeroOneStaticCookExecutedThisInvocation"] is True
        assert integration["actualZeroOneStaticArtifactLoaded"] is True
        assert integration["cacheValidated"] is True
        assert integration["actualZeroOneDynamicDeformationExecuted"] is False
        assert integration["actualZeroOneGpuRuntimeExecuted"] is False
        assert integration["actualZeroOneMobileRuntimeExecuted"] is False
        assert integration["fallbackPreserved"] is True
        assert integration["canonicalAuthorityPreserved"] is True
        assert integration["deterministicDerivative"] is True
        assert report["canonicalPackageBytesUnchanged"] is True
        assert report["cleanRunA"]["cacheState"] == "miss"
        assert report["cacheHitRun"]["cacheState"] == "hit"
        assert report["cacheHitRun"]["actualZeroOneStaticCookExecutedThisInvocation"] is False
        assert report["cacheHitRun"]["actualZeroOneStaticArtifactLoaded"] is True
        assert report["cleanRunB"]["cacheState"] == "miss"
        assert {
            report["cleanRunA"]["canonicalDerivativeHash"],
            report["cacheHitRun"]["canonicalDerivativeHash"],
            report["cleanRunB"]["canonicalDerivativeHash"],
            report["canonicalDerivativeHash"],
        } == {report["canonicalDerivativeHash"]}
        assert len(report["canonicalAuthorityHashes"]) == 6
        assert all(
            SHA256_RE.fullmatch(value) for value in report["canonicalAuthorityHashes"].values()
        )
        assert len(report["outputHashes"]) == 7
        assert all(SHA256_RE.fullmatch(entry["sha256"]) for entry in report["outputHashes"])
        assert report["assetAudit"]["meshCount"] > 0
        assert report["assetAudit"]["triangleCount"] > 0
        assert report["assetAudit"]["clusterCount"] > 0
        assert report["cleanRunA"]["peakMemoryBytes"] > 0
        assert report["globalPhase10Complete"] is False
        assert row["namespaceAudit"]["status"] == "historical_derivative_valid_v1"
        assert row["namespaceAudit"]["validationContract"] == (
            "legacy_v1_without_exact_namespace_manifest"
        )

    rebuild = rows["tshirt"]["deleteAndRebuild"]
    assert rebuild["executed"] is True
    assert rebuild["passed"] is True
    assert rebuild["fallbackPreserved"] is True
    assert rebuild["canonicalDerivativeHashBefore"] == rebuild["canonicalDerivativeHashAfter"]

    acceptance = evidence["acceptance"]
    assert acceptance["actualZeroOneStaticCookExecutedThisInvocation"] is True
    assert acceptance["actualZeroOneStaticArtifactLoaded"] is True
    assert acceptance["cacheValidated"] is True
    assert acceptance["actualZeroOneDynamicDeformationExecuted"] is False
    assert acceptance["actualZeroOneGpuRuntimeExecuted"] is False
    assert acceptance["actualZeroOneMobileRuntimeExecuted"] is False
    assert acceptance["allCanonicalAuthoritiesPreserved"] is True
    assert acceptance["allFallbacksPreserved"] is True
    assert acceptance["allDerivativesDeterministic"] is True
    assert acceptance["allHistoricalNamespacesValidatedUnderV1"] is True
    assert acceptance["allNamespacesValidUnderExactManifestV2"] is False
    assert acceptance["historicalScopedGateZ1Passed"] is True
    assert acceptance["globalZ1Passed"] is False
    assert acceptance["globalPhase10Complete"] is False
    assert set(acceptance["remainingBlockers"]) == {
        "turntable_or_human_visual_review",
        "broader_garment_provider_evidence",
        "mobile_profile",
    }
