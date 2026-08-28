from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import write_canonical_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Sanitize historical Phase 10 evidence.")
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--trusted-build-record", required=True, type=Path)
    args = parser.parse_args()
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    trusted = json.loads(args.trusted_build_record.read_text(encoding="utf-8"))
    migrated = _migrate(evidence)
    migrated["schemaVersion"] = "closy.zeroone.execution-evidence.v2"
    migrated["scope"] = "historical_local_cpu_static_tshirt_and_layered_asymmetric"
    migrated["axes"] = {
        "computeProfile": "D0",
        "dataProvenance": "project-authored synthetic",
        "executionProfile": "CPU",
        "gateScope": "static ZeroOne",
    }
    migrated["evidenceClassification"] = {
        "historicalLocalPass": True,
        "currentMasterRequalified": False,
        "durableWorkflowArtifact": False,
        "globalZ1Pass": False,
    }
    migrated["currentZeroOneMasterAnchor"] = "a17762bc1fc12fbd33f0488634635a5dcfdf8da3"
    migrated["trustedBuildRecord"] = trusted
    migrated["commandTemplate"] = [
        "python",
        "scripts/generate_zeroone_integration_evidence.py",
        "--executable",
        "<trusted-zeroone-executable>",
        "--trusted-build-record",
        "closy-forge/docs/evidence/phase10_zeroone_static/trusted_build_record.json",
        "--zeroone-repo",
        "<exact-zeroone-source-checkout>",
        "--work-root",
        "<managed-work-root>",
        "--output",
        "closy-forge/docs/evidence/phase10_zeroone_static/execution_evidence.json",
        "--closy-sha",
        "13c3d281843750c7bcd9db50e309ed129066e9fe",
        "--zeroone-sha",
        "c6388cbbf53ba8a47831ec25e83808e1edf32194",
    ]
    migrated.pop("command", None)
    migrated["host"] = {
        "platform": "windows",
        "architecture": "x86_64",
        "python": str(evidence.get("host", {}).get("python", "3.11")),
    }
    migrated["closy"].pop("draftPullRequest", None)
    migrated["closy"]["evidenceRole"] = "historical_paired_source"
    migrated["zeroOne"].pop("draftPullRequest", None)
    migrated["zeroOne"]["evidenceRole"] = "historical_owner_closed_unmerged_source"
    acceptance = migrated["acceptance"]
    acceptance.pop("scopedGateZ1Passed", None)
    acceptance["historicalScopedGateZ1Passed"] = True
    acceptance["globalZ1Passed"] = False
    acceptance["cacheValidated"] = True
    historical_namespaces = acceptance.pop("allNamespacesValid", None)
    if historical_namespaces is not None:
        acceptance["allHistoricalNamespacesValidatedUnderV1"] = historical_namespaces
    acceptance["allNamespacesValidUnderExactManifestV2"] = False
    for garment in migrated["garments"]:
        namespace = garment["namespaceAudit"]
        if namespace.get("status") == "derivative_valid":
            namespace["status"] = "historical_derivative_valid_v1"
        namespace["validationContract"] = "legacy_v1_without_exact_namespace_manifest"
    write_canonical_json(args.evidence, migrated)
    return 0


def _migrate(value: Any) -> Any:
    if isinstance(value, list):
        return [_migrate(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: _migrate(item) for key, item in value.items()}
    runtime = result.pop("actualZeroOneRuntimeExecuted", None)
    compute = result.pop("actualZeroOneComputeExecuted", None)
    if isinstance(runtime, bool) or isinstance(compute, bool):
        executed = runtime is True and compute is True
        cache_state = result.get("cacheState")
        result["actualZeroOneStaticCookExecutedThisInvocation"] = executed and cache_state != "hit"
        result["actualZeroOneStaticArtifactLoaded"] = executed
        result["cacheValidated"] = cache_state == "hit" or result.get("cacheValidated") is True
        result["actualZeroOneDynamicDeformationExecuted"] = False
        result["actualZeroOneGpuRuntimeExecuted"] = False
        result["actualZeroOneMobileRuntimeExecuted"] = False
    if result.get("contractVersion") == "closy.zeroone.integration-result.v1":
        result["schemaVersion"] = 2
        result["contractVersion"] = "closy.zeroone.integration-result.v2"
        result["cacheValidated"] = True
    return result


if __name__ == "__main__":
    raise SystemExit(main())
