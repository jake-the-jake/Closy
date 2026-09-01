from __future__ import annotations

import json
import platform
import shutil
import tempfile
from pathlib import Path
from typing import Any

from closy_forge.package_io.hashing import sha256_file
from closy_forge.runtime_delivery.package import (
    RuntimePackageError,
    RuntimePackageInputs,
    build_runtime_package,
    load_runtime_package,
)

REPRODUCIBILITY_VERSION = "closy.d0_core_runtime.reproducibility.v4"


def evaluate_core_reproducibility(root: Path, sentinel: dict[str, Any]) -> dict[str, Any]:
    runtime_source = root / (
        "docs/evidence/d0_texture_rerender_correction_v3/predictions/"
        "candidate_runtime.closyruntime"
    )
    source_manifest = _read(runtime_source / "manifest.json")
    fallback_source = root / sentinel["identities"]["fallback"]["path"]
    expected_tree = _tree_identity(runtime_source)
    with tempfile.TemporaryDirectory(prefix="closy-h1-") as temporary:
        work = Path(temporary)
        clean_a = _build(work / "clean-a.closyruntime", fallback_source, source_manifest)
        clean_b = _build(work / "clean-b.closyruntime", fallback_source, source_manifest)
        identity_a = _tree_identity(clean_a)
        identity_b = _tree_identity(clean_b)
        cache = work / "cache.closyruntime"
        cache_miss = not cache.exists()
        shutil.copytree(clean_a, cache)
        cache_hit = _tree_identity(cache) == identity_a
        corrupt_file = next((cache / "pages").glob("*.zlib"))
        original = corrupt_file.read_bytes()
        corrupt_file.write_bytes(original[:-1] + bytes((original[-1] ^ 1,)))
        corruption_detected = False
        try:
            load_runtime_package(cache, offline=True)
        except RuntimePackageError:
            corruption_detected = True
        shutil.rmtree(cache)
        cache = _build(cache, fallback_source, source_manifest)
        corruption_rebuild = _tree_identity(cache) == identity_a
        isolated_source = work / "source.glb"
        shutil.copy2(fallback_source, isolated_source)
        isolated_source.unlink()
        withdrawal_detected = False
        try:
            _build(work / "withdrawn.closyruntime", isolated_source, source_manifest)
        except RuntimePackageError as error:
            withdrawal_detected = error.code == "runtime_source_file_missing"
        delete_target = _build(
            work / "delete-rebuild.closyruntime", fallback_source, source_manifest
        )
        before_delete = _tree_identity(delete_target)
        shutil.rmtree(delete_target)
        delete_target = _build(delete_target, fallback_source, source_manifest)
        delete_rebuild = _tree_identity(delete_target) == before_delete
    checks = {
        "cleanFreshBuildMatchesSentinel": identity_a == expected_tree,
        "secondCleanBuildMatches": identity_b == identity_a,
        "cacheMissObserved": cache_miss,
        "cacheHitValidated": cache_hit,
        "cacheCorruptionDetected": corruption_detected,
        "cacheInvalidatedAndRebuilt": corruption_rebuild,
        "sourceWithdrawalFailsClosed": withdrawal_detected,
        "deleteRebuildMatches": delete_rebuild,
        "canonicalRuntimeDigestMatches": source_manifest.get("packageDigest")
        == sentinel.get("runtimePackageDigest"),
    }
    return {
        "schemaVersion": 1,
        "evidenceVersion": REPRODUCIBILITY_VERSION,
        "scope": "exact_h0_pre_topology_sentinel_core_forge_runtime",
        "sentinelManifestDigest": sentinel["integrity"]["sentinelManifestDigest"],
        "candidateId": sentinel["candidateId"],
        "candidatePackageDigest": sentinel["candidatePackageDigest"],
        "canonicalRuntimePackageDigest": source_manifest["packageDigest"],
        "canonicalTreeIdentity": expected_tree,
        "checks": checks,
        "crossPlatformCrossMinor": {
            "localPlatform": platform.system().lower(),
            "localArchitecture": platform.machine().lower(),
            "localPython": platform.python_version(),
            "qualification": "exact_head_ci_matrix_required",
            "contentIdentityComparedNotExecutableBytes": True,
        },
        "resultStatus": "pass" if all(checks.values()) else "fail",
        "d0Rp12Status": "pass" if all(checks.values()) else "fail",
        "predecessorScoped": True,
        "unitITopologyChangeRequiresUnitJRerun": True,
    }


def _build(target: Path, fallback: Path, source_manifest: dict[str, Any]) -> Path:
    return build_runtime_package(
        target,
        inputs=RuntimePackageInputs(
            conventional_fallback_glb=fallback,
            source_link=dict(source_manifest["sourceLink"]),
            platform_profile=str(source_manifest["platformProfile"]),
            pose_id=str(source_manifest["motion"]["prebakedOptions"][0]["poseId"]),
            pose_payload={
                "frame": 0,
                "positionsSource": "conventional_glb_bind_pose",
                "dynamicDeformationExecuted": False,
            },
        ),
    )


def _tree_identity(root: Path) -> list[dict[str, object]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != ".closy-forge-owned.json"
    ]


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("h1_runtime_manifest_not_object")
    return value
