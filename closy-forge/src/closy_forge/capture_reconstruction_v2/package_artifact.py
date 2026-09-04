from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from .common import canonical_bytes, canonical_digest, sha256_bytes, write_json

PACKAGE_FILES = (
    "pattern/pattern.json",
    "semantic/semantic_graph.json",
    "simulation/rest_mesh.json",
    "simulation/settle_receipt.json",
    "render/render_mesh.json",
    "binding/simulation_to_render.json",
    "materials/material_descriptor.json",
    "appearance/appearance.json",
    "fit/fit_report.json",
    "provenance/evidence.json",
)


def retain_candidate_package(
    root: Path,
    session_id: str,
    fit: dict[str, Any],
    appearance: dict[str, Any],
) -> dict[str, Any]:
    package_root = root / session_id
    package = dict(fit.get("package", {}))
    pattern = dict(package.get("pattern", {}))
    semantic = _semantic_graph(pattern)
    payloads: dict[str, Any] = {
        "pattern/pattern.json": pattern,
        "semantic/semantic_graph.json": semantic,
        "simulation/rest_mesh.json": package.get("simulationMesh", {}),
        "simulation/settle_receipt.json": package.get("solver", {}),
        "render/render_mesh.json": package.get("renderMesh", {}),
        "binding/simulation_to_render.json": package.get("simulationToRenderBinding", {}),
        "materials/material_descriptor.json": package.get("materialDescriptor", {}),
        "appearance/appearance.json": appearance,
        "fit/fit_report.json": {key: value for key, value in fit.items() if key != "package"},
        "provenance/evidence.json": package.get("provenance", {}),
    }
    for relative, payload in payloads.items():
        write_json(package_root / relative, payload)
    inventory = _inventory(payloads)
    receipt: dict[str, Any] = {
        "schemaVersion": 2,
        "receiptVersion": "closy.capture_v2_package_stage_receipt.v2",
        "sessionId": session_id,
        "terminalOutcome": fit.get("terminalOutcome"),
        "intrinsicPackageValid": package.get("intrinsicPackageValid", False),
        "geometryTopologyValid": package.get("geometryTopologyValid", False),
        "simulationReady": package.get("simulationReady", False),
        "bindingValid": package.get("bindingValid", False),
        "appearanceComplete": bool(appearance.get("baseColorSha256")),
        "qualificationEligible": False,
        "runtimeRouteEligible": False,
        "globalProjectCanonicalAcceptance": False,
        "inventoryDigest": canonical_digest(inventory),
    }
    receipt["receiptDigest"] = canonical_digest(receipt)
    write_json(package_root / "stage_receipt.json", receipt)
    payloads["stage_receipt.json"] = receipt
    inventory = _inventory(payloads)
    manifest: dict[str, Any] = {
        "schemaVersion": 2,
        "packageVersion": "closy.capture_reconstruction_candidate_package.v2",
        "sessionId": session_id,
        "family": fit.get("family"),
        "mode": fit.get("mode"),
        "intrinsicPackageValid": package.get("intrinsicPackageValid", False),
        "geometryTopologyValid": package.get("geometryTopologyValid", False),
        "simulationReady": package.get("simulationReady", False),
        "bindingValid": package.get("bindingValid", False),
        "appearanceComplete": bool(appearance.get("baseColorSha256")),
        "evidenceQualificationEligible": False,
        "runtimeRouteEligible": False,
        "globalProjectCanonicalAcceptance": False,
        "inventory": inventory,
        "canonicalPackageDigest": canonical_digest(inventory),
    }
    manifest["manifestDigest"] = canonical_digest(manifest)
    write_json(package_root / "manifest.json", manifest)
    return manifest


def validate_retained_package(root: Path) -> list[str]:
    failures: list[str] = []
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return ["capture_package_manifest_missing"]
    import json

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    inventory = manifest.get("inventory")
    if not isinstance(inventory, list):
        return ["capture_package_inventory_missing"]
    expected = {str(row.get("path")) for row in inventory}
    if any(not _safe_package_member(path) for path in expected):
        return ["capture_package_inventory_path_unsafe"]
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    if expected != actual:
        failures.append("capture_package_inventory_path_mismatch")
    for row in inventory:
        path = root / str(row["path"])
        if not path.is_file():
            continue
        payload = path.read_bytes()
        if len(payload) != int(row["byteLength"]) or sha256_bytes(payload) != row["sha256"]:
            failures.append("capture_package_inventory_digest_mismatch")
    if manifest.get("canonicalPackageDigest") != canonical_digest(inventory):
        failures.append("capture_package_digest_invalid")
    if manifest.get("manifestDigest") != canonical_digest(manifest, "manifestDigest"):
        failures.append("capture_package_manifest_digest_invalid")
    return sorted(set(failures))


def retained_package_inventory(root: Path) -> dict[str, Any]:
    packages = sorted(path.parent for path in root.glob("*/manifest.json"))
    rows = []
    for package in packages:
        manifest = (package / "manifest.json").read_bytes()
        rows.append(
            {
                "sessionId": package.name,
                "manifestSha256": sha256_bytes(manifest),
                "validationFailures": validate_retained_package(package),
            }
        )
    return {
        "packageCount": len(rows),
        "rows": rows,
        "inventoryDigest": canonical_digest(rows),
    }


def _inventory(payloads: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "path": path,
            "byteLength": len(canonical_bytes(payload)),
            "sha256": sha256_bytes(canonical_bytes(payload)),
        }
        for path, payload in sorted(payloads.items())
    ]


def _safe_package_member(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        bool(value)
        and "\\" not in value
        and not path.is_absolute()
        and ".." not in path.parts
        and "." not in path.parts
    )


def _semantic_graph(pattern: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": 2,
        "graphVersion": "closy.capture_v2_structured_garment_authority.v1",
        "garmentClass": pattern.get("garmentClass"),
        "panels": [
            {"id": panel.get("id"), "semanticRole": panel.get("semanticRole")}
            for panel in pattern.get("panels", [])
        ],
        "seams": [
            {"id": seam.get("id"), "spans": seam.get("spans", [])}
            for seam in pattern.get("seams", [])
        ],
        "openings": pattern.get("openings", []),
        "canonicalAuthorityRetained": True,
    }
