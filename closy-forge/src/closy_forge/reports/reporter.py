from __future__ import annotations

from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import read_json


def summarize_package(package_dir: Path) -> dict[str, Any]:
    manifest = read_json(package_dir / "manifest.json")
    summary = read_json(package_dir / "reports" / "summary.json")
    binding = read_json(package_dir / "binding" / "binding_manifest.json")
    validation = read_json(package_dir / "reports" / "package_validation.json")
    return {
        "schemaVersion": manifest["schemaVersion"],
        "garmentId": manifest["garmentId"],
        "garmentClass": manifest["garmentClass"],
        "avatarContractId": manifest["avatar"]["contractId"],
        "coordinateConvention": manifest["coordinateConvention"]["id"],
        "packageDigest": manifest["canonicalPackageDigest"],
        "seed": manifest["seed"],
        "buildProfile": manifest["buildProfile"],
        "capabilities": manifest["capabilities"],
        "counts": summary["counts"],
        "packageByteSize": sum(entry["byteSize"] for entry in manifest["inventory"]),
        "fileSizes": {entry["path"]: entry["byteSize"] for entry in manifest["inventory"]},
        "topologyHashes": manifest["hashes"],
        "binding": {
            "recordCount": binding["recordCount"],
            "maxError": binding["maximumReconstructionError"],
            "rmsError": binding["rmsReconstructionError"],
        },
        "validation": validation["counts"],
        "warnings": manifest["warnings"],
    }


def human_report(package_dir: Path) -> str:
    summary = summarize_package(package_dir)
    lines = [
        f"Closy garment package: {summary['garmentId']}",
        f"Class: {summary['garmentClass']}  Avatar: {summary['avatarContractId']}",
        f"Schema: {summary['schemaVersion']}  Seed: {summary['seed']}",
        f"Convention: {summary['coordinateConvention']}",
        f"Package digest: {summary['packageDigest']}",
        f"Inventoried bytes: {summary['packageByteSize']}",
        "Counts:",
    ]
    for key, value in summary["counts"].items():
        lines.append(f"  - {key}: {value}")
    binding = summary["binding"]
    lines.extend(
        [
            (
                f"Binding: {binding['recordCount']} records, "
                f"max error {binding['maxError']:.8f}, RMS {binding['rmsError']:.8f}"
            ),
            f"Validation: {summary['validation']}",
            "Warnings: " + ", ".join(summary["warnings"]),
            "ZeroOne: unavailable and optional",
            "Cloth settle: not run (analytic fixture only)",
        ]
    )
    return "\n".join(lines) + "\n"
