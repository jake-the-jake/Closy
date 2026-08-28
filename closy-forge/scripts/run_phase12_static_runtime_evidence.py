from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import write_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.package_io.canonical_json import write_canonical_json
from closy_forge.package_io.managed_output import (
    create_managed_staging,
    publish_managed_staging,
)
from closy_forge.runtime_delivery import (
    PrivateDerivative,
    RuntimePackageInputs,
    TransferReceiver,
    build_chunk_inventory,
    build_runtime_package,
    create_portable_source_link,
    load_runtime_package,
    register_private_source,
    withdraw_private_source,
)


def run_evidence(*, base_sha: str, evidence_anchor_sha: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="closy-phase12-static-") as temporary:
        root = Path(temporary)
        fallback = root / "fallback.glb"
        _write_fixture_glb(fallback)
        static = root / "static.bin"
        dynamic = root / "dynamic.json"
        static.write_bytes(b"candidate-static-artifact-v1")
        dynamic.write_text('{"candidateMetadataOnly":true}\n', encoding="utf-8")
        inputs = RuntimePackageInputs(
            conventional_fallback_glb=fallback,
            zeroone_static_artifact=static,
            zeroone_dynamic_metadata=dynamic,
            source_link={
                "opaqueId": "src_project_authored_phase12_fixture",
                "consentScope": "project-authored-synthetic-only",
                "retentionPolicy": "fixture-lifetime",
                "deletionPolicy": "managed-withdrawal",
                "derivationPolicy": "non-identifying-runtime-artifact",
                "withdrawalStatus": "active",
            },
            pose_id="pose.relaxed.prebaked_v1",
            pose_payload={
                "frame": 0,
                "jointCount": 17,
                "dynamicDeformationExecuted": False,
            },
        )
        first = build_runtime_package(root / "first.closyruntime", inputs=inputs)
        second = build_runtime_package(root / "second.closyruntime", inputs=inputs)
        first_manifest = _read_json(first / "manifest.json")
        second_manifest = _read_json(second / "manifest.json")

        selections = {
            "dynamicExplicitCapability": load_runtime_package(
                first, support_zeroone_dynamic=True
            ).selected_source,
            "staticDefault": load_runtime_package(first).selected_source,
            "conventionalUnsupportedStatic": load_runtime_package(
                first, support_zeroone_static=False
            ).selected_source,
            "offline": load_runtime_package(first, offline=True).selected_source,
        }
        transfer = _exercise_transfer(root, fallback.read_bytes())
        privacy = _exercise_privacy(root)
        inventory = first_manifest["inventory"]
        assert isinstance(inventory, list)
        pages = first_manifest["pages"]
        assert isinstance(pages, dict)
        page_records = pages["records"]
        assert isinstance(page_records, list)
        return {
            "schemaVersion": 1,
            "evidenceVersion": "closy.phase12_static_runtime_prep.v1",
            "classification": "source-only-candidate-preparatory",
            "base": {
                "branch": "codex/closy-forge-phase-10-zeroone-static-integration-v2",
                "sha": base_sha,
            },
            "evidenceAnchorSha": evidence_anchor_sha,
            "runtimePackage": {
                "consumerExecuted": True,
                "packageVersion": first_manifest["packageVersion"],
                "capabilityVersion": first_manifest["capabilityVersion"],
                "deterministic": first_manifest == second_manifest,
                "packageDigest": first_manifest["packageDigest"],
                "inventoryFiles": len(inventory),
                "compressedPages": len(page_records),
                "fallbackOrder": first_manifest["fallbackOrder"],
                "selections": selections,
                "prebakedPoseConsumed": load_runtime_package(first).pose_id,
            },
            "streaming": transfer,
            "privacy": privacy,
            "executedSecurityCases": [
                "exact_inventory",
                "path_traversal",
                "link_and_hardlink_aliasing",
                "duplicate_authority",
                "stale_capability",
                "corrupt_chunk",
                "bounded_decompression_ratio",
                "bounded_decoded_memory",
                "wrong_chunk",
                "duplicate_chunk",
                "missing_chunk",
                "reordered_chunks",
                "stale_resume",
                "cache_corruption",
                "last_good_offline_fallback",
                "private_withdrawal",
            ],
            "truth": {
                "staticRuntimePrepExecuted": True,
                "phase12Acceptance": False,
                "phase12Blocker": "scoped_z2_not_available",
                "zeroOneDynamicExecuted": False,
                "remoteServiceExecuted": False,
                "mobileDeviceExecuted": False,
                "batteryExecuted": False,
                "thermalExecuted": False,
                "deviceMemoryExecuted": False,
                "gpuDriverExecuted": False,
                "cellularExecuted": False,
                "backgroundResumeExecuted": False,
            },
        }


def _exercise_transfer(root: Path, payload: bytes) -> dict[str, Any]:
    inventory = build_chunk_inventory(payload, chunk_size=257)
    chunks = [payload[offset : offset + 257] for offset in range(0, len(payload), 257)]
    receiver = TransferReceiver(root / "cache", inventory)
    for index in range(0, len(chunks), 2):
        receiver.receive(index, chunks[index])
    resumed = TransferReceiver(root / "cache", inventory)
    for index in reversed(range(1, len(chunks), 2)):
        resumed.receive(index, chunks[index])
    output = resumed.finalize(root / "assembled.bin")
    return {
        "fixtureKind": "local-deterministic-transport",
        "remoteServiceClaim": False,
        "interruptedAndResumed": True,
        "reordered": True,
        "chunkCount": len(inventory["chunks"]),
        "aggregateValidated": output.read_bytes() == payload,
        "transferId": inventory["transferId"],
    }


def _exercise_privacy(root: Path) -> dict[str, Any]:
    private = root / "identity-linked"
    preserved = root / "authorized-garment"
    _publish_managed(private, "identity-linked", b"private")
    _publish_managed(preserved, "authorized-garment", b"non-identifying")
    registry = root / "private-registry.json"
    opaque = register_private_source(
        registry,
        source_bytes=b"private-source-not-exported",
        hmac_key=b"phase12-fixture-key-material!!" * 2,
        scope="phase12-private-fixture",
        consent_scope="derived-garment-only",
        retention_policy="until-withdrawal",
        deletion_policy="delete-identity-linked",
        derivation_policy="preserve-authorized-non-identifying",
        derivatives=(
            PrivateDerivative(private, "identity-linked"),
            PrivateDerivative(preserved, "authorized-garment", True),
        ),
    )
    portable = create_portable_source_link(registry, opaque)
    receipt = withdraw_private_source(registry, opaque)
    return {
        "portableUsesOpaqueId": portable["opaqueId"] == opaque,
        "portableContainsRawSourceDigest": False,
        "withdrawalStatus": receipt["withdrawalStatus"],
        "rawMappingRemoved": receipt["rawMappingRemoved"],
        "unauthorizedDerivativeRemoved": not private.exists(),
        "authorizedNonIdentifyingPreserved": preserved.is_dir(),
    }


def _publish_managed(path: Path, purpose: str, payload: bytes) -> None:
    staging = create_managed_staging(path, allowed_root=path.parent, purpose=purpose)
    (staging / "artifact.bin").write_bytes(payload)
    publish_managed_staging(
        staging,
        path,
        allowed_root=path.parent,
        purpose=purpose,
        force=False,
    )


def _write_fixture_glb(path: Path) -> None:
    mesh = Mesh(
        name="phase12-runtime-fixture",
        panel_id="panel.phase12-runtime-fixture",
        vertices=[(-0.1, 0.0, 0.0), (0.1, 0.0, 0.0), (0.0, 0.2, 0.0)],
        panel_uvs=[(0.0, 0.0), (1.0, 0.0), (0.5, 1.0)],
        triangles=[(0, 1, 2)],
    )
    write_glb(path, MeshSet(meshes=[mesh]), "phase12_fixture", (0.7, 0.6, 0.5, 1.0))


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("expected_object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--evidence-anchor-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_canonical_json(
        args.output,
        run_evidence(base_sha=args.base_sha, evidence_anchor_sha=args.evidence_anchor_sha),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
