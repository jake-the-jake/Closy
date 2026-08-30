from __future__ import annotations

from pathlib import Path
from typing import Any

from closy_forge.package_io.canonical_json import read_json
from closy_forge.zeroone.dynamic_namespace import DYNAMIC_DIRECTORY
from closy_forge.zeroone.mechanical_reference_surface import (
    MECHANICAL_REFERENCE_MANIFEST_PATH,
)

INTEGRATED_IDENTITY_KEYS = (
    "canonicalPackageDigest",
    "patternHash",
    "simulationTopologyHash",
    "renderTopologyHash",
    "bindingHash",
    "conventionalFallbackHash",
    "mechanicalReferenceSurfaceHash",
    "staticDerivativeIdentity",
    "dynamicRequestIdentity",
    "dynamicOutputIdentity",
    "zeroOneBinaryIdentity",
    "avatarAuthorityHash",
    "avatarFitDigest",
    "layerProfileIdentity",
    "outfitSurfaceIdentity",
)

_CAPABILITY_DEPENDENCIES = {
    "conventional_static_fallback": {
        "canonicalPackageDigest",
        "conventionalFallbackHash",
    },
    "candidate_static_zeroone": {
        "canonicalPackageDigest",
        "conventionalFallbackHash",
        "mechanicalReferenceSurfaceHash",
        "staticDerivativeIdentity",
        "zeroOneBinaryIdentity",
    },
    "mt1_reference_motion_d0": {
        "simulationTopologyHash",
        "renderTopologyHash",
        "bindingHash",
        "mechanicalReferenceSurfaceHash",
        "staticDerivativeIdentity",
        "dynamicRequestIdentity",
        "dynamicOutputIdentity",
        "zeroOneBinaryIdentity",
    },
    "conventional_c3_deformation": {
        "canonicalPackageDigest",
        "simulationTopologyHash",
        "renderTopologyHash",
        "bindingHash",
    },
    "synthetic_avatar_fit_d0": {
        "avatarAuthorityHash",
        "avatarFitDigest",
    },
    "geometric_layer_collision_d0": {
        "simulationTopologyHash",
        "renderTopologyHash",
        "avatarAuthorityHash",
        "avatarFitDigest",
        "layerProfileIdentity",
        "outfitSurfaceIdentity",
    },
}


def build_reference_motion_invalidation_ledger(
    package_dir: Path,
    *,
    closy_source_sha: str,
    zeroone_source_sha: str,
    zeroone_binary_sha256: str,
) -> dict[str, Any]:
    package = package_dir.resolve(strict=True)
    package_manifest = _object(package / "manifest.json")
    simulation = _object(package / "simulation" / "mesh_manifest.json")
    render = _object(package / "render" / "mesh_manifest.json")
    binding = _object(package / "binding" / "production_binding_contract.json")
    mt1 = _object(package / MECHANICAL_REFERENCE_MANIFEST_PATH)
    static_derivative = _object(
        package / "zeroone" / "static-d0" / "derivative" / "derivative.json"
    )
    dynamic_root = package / "zeroone" / DYNAMIC_DIRECTORY
    request_summary = _object(dynamic_root / "request_summary.json")
    execution = _object(dynamic_root / "execution.json")
    simulation_provenance = simulation.get("provenance")
    provenance_record = simulation_provenance if isinstance(simulation_provenance, dict) else {}
    inventory = {
        str(row["path"]): row
        for row in package_manifest.get("inventory", [])
        if isinstance(row, dict) and isinstance(row.get("path"), str)
    }
    identities = {
        "patternHash": _inventory_sha(inventory, "pattern/pattern.json"),
        "panelBoundarySamplingHash": _inventory_sha(inventory, "pattern/panels.svg"),
        "simulationProvenance": simulation_provenance,
        "triangulator": provenance_record.get("triangulator"),
        "triangulatorVersion": provenance_record.get("triangulatorVersion"),
        "triangulatorIdentityAvailable": bool(
            provenance_record.get("triangulator") and provenance_record.get("triangulatorVersion")
        ),
        "seamOpeningGraphHash": _inventory_sha(inventory, "semantic/garment_graph.json"),
        "restTopologyHash": simulation.get("topologyHash"),
        "restContentHash": _object(package / "simulation" / "rest_state.json").get(
            "meshContentHash"
        ),
        "settledTopologyHash": simulation.get("topologyHash"),
        "settledContentHash": simulation.get("contentHash"),
        "renderTopologyHash": render.get("topologyHash"),
        "renderContentHash": render.get("contentHash"),
        "bindingHash": binding.get("integrity", {}).get("productionBindingContractHash"),
        "historicalProcessingSurfaceHash": _inventory_sha(
            inventory, "zeroone/input-z2-v1/processing_surface.glb", required=False
        ),
        "mechanicalReferenceSurfaceHash": mt1.get("hashes", {}).get("surfaceSha256"),
        "staticDerivativeIdentity": request_summary.get("staticDerivativeIdentitySha256"),
        "dynamicRequestIdentity": request_summary.get("requestSha256"),
        "dynamicOutputIdentity": execution.get("outputSha256"),
        "zeroOneSourceIdentity": zeroone_source_sha,
        "zeroOneBinaryIdentity": zeroone_binary_sha256,
        "appearanceMaterialHash": _inventory_sha(
            inventory, "textures/pbr_material_maps.json", required=False
        ),
    }
    return {
        "schemaVersion": 1,
        "ledgerVersion": "closy.representation-invalidation-ledger.v2",
        "profileId": mt1["profile"],
        "closyGenerationSourceSha": closy_source_sha,
        "canonicalPackageDigest": package_manifest.get("canonicalPackageDigest"),
        "identities": identities,
        "calculatedInvalidation": {
            "changedIdentityClasses": [
                "mechanical_reference_surface",
                "static_derivative_source",
                "dynamic_clip_request_output",
                "zeroone_processor_binary_source",
            ],
            "preservedIdentityClasses": [
                "pattern_boundary_seams_openings",
                "canonical_simulation_topology_content",
                "settled_topology_content",
                "canonical_render_dense_topology_content",
                "production_binding",
                "canonical_fallback",
                "appearance_material",
            ],
            "mandatoryReruns": [
                "static_cook_exact_mechanical_reference",
                "mt1_dynamic_request_and_independent_oracle",
                "zeroone_exact_head_qualification",
            ],
            "retainedByExactIdentity": [
                "C3-v1",
                "canonical_package_validation",
                "Z1-nine-family-historical-inputs",
                "PR34-Z2-failure-evidence",
            ],
            "notInvalidated": ["canonical_package_identity", "fallback_runtime"],
        },
        "gateApplicability": {
            "C3": {"status": "retained_exact_identity", "profile": "C3-v1"},
            "Z1": {"status": "new_static_source_qualified_global_partial"},
            "MT1": {"status": "see_mechanical_reference_namespace"},
            "Z2": {"status": "partial_not_solver_driven"},
            "PHY1": {"status": "not_implied"},
        },
        "evidenceLocations": {
            "surface": MECHANICAL_REFERENCE_MANIFEST_PATH,
            "static": "zeroone/static-d0",
            "dynamic": f"zeroone/{DYNAMIC_DIRECTORY}",
        },
        "staticDerivativeSourcePath": static_derivative.get("source", {}).get(
            "inputAssetRelativePath"
        ),
    }


def build_integrated_runtime_invalidation_ledger(
    baseline: dict[str, str], current: dict[str, str]
) -> dict[str, Any]:
    """Calculate capability invalidation from exact representation identity changes."""

    _validate_integrated_identities(baseline)
    _validate_integrated_identities(current)
    changed = sorted(key for key in INTEGRATED_IDENTITY_KEYS if baseline[key] != current[key])
    changed_set = set(changed)
    invalidated = sorted(
        capability
        for capability, dependencies in _CAPABILITY_DEPENDENCIES.items()
        if dependencies & changed_set
    )
    retained = sorted(set(_CAPABILITY_DEPENDENCIES) - set(invalidated))
    mandatory_reruns = sorted(
        {rerun for capability in invalidated for rerun in _reruns_for(capability)}
    )
    return {
        "schemaVersion": 1,
        "ledgerVersion": "closy.integrated-representation-invalidation-ledger.d0.v1",
        "baselineIdentities": dict(sorted(baseline.items())),
        "currentIdentities": dict(sorted(current.items())),
        "dependencyRules": {
            capability: sorted(dependencies)
            for capability, dependencies in sorted(_CAPABILITY_DEPENDENCIES.items())
        },
        "calculatedInvalidation": {
            "changedIdentityClasses": changed,
            "invalidatedCapabilities": invalidated,
            "retainedByExactIdentity": retained,
            "mandatoryReruns": mandatory_reruns,
            "failClosed": True,
        },
    }


def validate_integrated_runtime_invalidation_ledger(
    ledger: dict[str, Any], expected_current: dict[str, str]
) -> list[str]:
    issues: list[str] = []
    baseline = ledger.get("baselineIdentities")
    current = ledger.get("currentIdentities")
    if not isinstance(baseline, dict) or not isinstance(current, dict):
        return ["integrated_invalidation_identity_maps_missing"]
    try:
        rebuilt = build_integrated_runtime_invalidation_ledger(baseline, expected_current)
    except ValueError as error:
        return [str(error)]
    if current != dict(sorted(expected_current.items())):
        issues.append("integrated_invalidation_current_identity_stale")
    if ledger != rebuilt:
        issues.append("integrated_invalidation_not_recalculated")
    return sorted(issues)


def _validate_integrated_identities(values: dict[str, str]) -> None:
    if set(values) != set(INTEGRATED_IDENTITY_KEYS):
        raise ValueError("integrated_invalidation_identity_inventory_invalid")
    for key, value in values.items():
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError(f"integrated_invalidation_identity_invalid:{key}")


def _reruns_for(capability: str) -> tuple[str, ...]:
    return {
        "conventional_static_fallback": ("runtime_package_validation",),
        "candidate_static_zeroone": ("zeroone_static_exact_identity_qualification",),
        "mt1_reference_motion_d0": ("mt1_dynamic_request_and_independent_oracle",),
        "conventional_c3_deformation": ("c3_binding_pose_suite",),
        "synthetic_avatar_fit_d0": ("synthetic_avatar_authority_fit_suite",),
        "geometric_layer_collision_d0": ("canonical_surface_outfit_clearance_suite",),
    }[capability]


def _inventory_sha(
    inventory: dict[str, dict[str, Any]], relative: str, *, required: bool = True
) -> str | None:
    row = inventory.get(relative)
    if row is None:
        if required:
            raise ValueError(f"invalidation_ledger_inventory_missing:{relative}")
        return None
    value = row.get("sha256")
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"invalidation_ledger_inventory_hash_invalid:{relative}")
    return value


def _object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"invalidation_ledger_object_required:{path.name}")
    return value
