"""Explicit read-only adapters for actual binding and whole-outfit runtime inputs."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from closy_forge.manual_provider_binding_v2.package import check_package_v2
from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_file
from closy_forge.package_layering_v1.solver import validate_output
from closy_forge.runtime_delivery.package_v3 import BINDING_CODEC, LOCAL_FRAME_CODEC


def prepare(binding: Path, outfit: Path, families: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise ValueError("representative_descriptor_requires_fresh_destination")
    b = check_package_v2(binding)
    b_hash = sha256_file(binding / "manifest.json")
    outfit_hash = sha256_file(outfit / "manifest.json")
    validate_output(outfit, trusted_manifest_hash=outfit_hash)
    manifest, report = read_json(outfit / "manifest.json"), read_json(outfit / "report.json")
    available = {
        m["packageIdentity"]: m
        for p in sorted(families.glob("*/*/manifest.json"))
        for m in [read_json(p)]
    }
    members = []
    for layer_id, identity in sorted(manifest["sources"].items()):
        if identity not in available:
            raise ValueError("representative_outfit_source_missing")
        m = available[identity]
        if m["avatarId"] != manifest["avatarId"]:
            raise ValueError("representative_outfit_avatar_mismatch")
        members.append(
            {
                "garmentId": f"{m['garmentId']}.layer.{layer_id}",
                "avatarId": m["avatarId"],
                "provenance": identity,
            }
        )
    result = {
        "version": "closy.runtime_representatives.development.v3",
        "scope": "geometry_delivery_not_fit_or_physical_readiness",
        "cases": [
            {
                "caseId": "representative-local-frame",
                "kind": "binding",
                "root": str(binding.resolve()),
                "manifest": "manifest.json",
                "manifestSha256": b_hash,
                "provenance": b_hash,
                "garmentId": f"garment.{b['sourceId']}",
                "avatarId": "avatar.manual-provider-reference.v1",
                "identityScope": "external_development_reference_not_personalized_avatar",
                "bindingCodec": LOCAL_FRAME_CODEC,
                "render": "render/clean.glb",
                "cage": "render/fallback.glb",
                "binding": "binding/local_frame_v2.bin",
                "members": [],
                "sourceQuality": {"status": b["status"], "rest": b["rest"]},
            },
            {
                "caseId": "representative-whole-outfit",
                "kind": "outfit",
                "root": str(outfit.resolve()),
                "manifest": "manifest.json",
                "manifestSha256": outfit_hash,
                "provenance": outfit_hash,
                "garmentId": manifest["garmentId"],
                "avatarId": manifest["avatarId"],
                "bindingCodec": BINDING_CODEC,
                "render": "render.glb",
                "cage": "simulation.glb",
                "binding": "binding.bin",
                "members": members,
                "sourceQuality": {
                    "fitReady": report["ready"],
                    "reportSha256": sha256_file(outfit / "report.json"),
                    "scope": "failed_fit_is_retained_even_if_delivery_passes",
                },
            },
        ],
    }
    write_canonical_json(output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True, type=Path)
    parser.add_argument("--outfit", required=True, type=Path)
    parser.add_argument("--families", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = prepare(args.binding, args.outfit, args.families, args.output)
    print(f"Prepared {len(result['cases'])} actual representative source descriptors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
