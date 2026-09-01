from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
from typing import Any

from closy_forge.appearance_correction_v3.freeze import IMPLEMENTATION_FREEZE_PATH
from closy_forge.appearance_correction_v3.protocol import PROTOCOL_SHA256, load_correction_protocol
from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file

IMPLEMENTATION_FILES = (
    "src/closy_forge/appearance_correction_v3/__init__.py",
    "src/closy_forge/appearance_correction_v3/controls.py",
    "src/closy_forge/appearance_correction_v3/freeze.py",
    "src/closy_forge/appearance_correction_v3/known_target.py",
    "src/closy_forge/appearance_correction_v3/prediction.py",
    "src/closy_forge/appearance_correction_v3/projection.py",
    "src/closy_forge/appearance_correction_v3/protocol.py",
    "src/closy_forge/appearance_correction_v3/source_inputs.py",
    "scripts/evaluate_d0_texture_rerender_v3_known_target.py",
    "scripts/freeze_d0_texture_rerender_v3_implementation.py",
    "scripts/generate_d0_texture_rerender_v3_prediction.py",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol-commit-sha", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    protocol = load_correction_protocol(root)
    records = [
        {"path": relative, "sha256": sha256_file(root / relative)}
        for relative in IMPLEMENTATION_FILES
    ]
    bundle_hash = sha256_bytes(canonical_dumps(records).encode("utf-8"))
    freeze: dict[str, Any] = {
        "schemaVersion": 1,
        "freezeId": "closy.d0_texture_rerender.implementation_freeze.v3",
        "protocolCommitSha": args.protocol_commit_sha,
        "protocolSha256": PROTOCOL_SHA256,
        "strategyId": "geometric_source_surface_atlas_projection",
        "strategyVersion": "closy.appearance.geometric_source_surface_atlas_projection.d0_v3",
        "configuration": {
            "atlasSize": 256,
            "sourceBackedBlendRadiusTexels": 6,
            "generatedFill": "deterministic_bounded_blue_fabric_prior_v1",
            "sourceObservedDenominator": "active_semantic_island_texels",
            "observedLogoOverwriteAllowed": False,
            "cameraIndependentFinalAtlas": True,
        },
        "sourceClosure": deepcopy(protocol["sourceClosure"]),
        "contestantClosure": {
            "candidateId": "candidate.d0_exact_fitted_topology_v2.060e8d4aaaa7e82eddb75880",
            "candidatePackageDigest": (
                "aa3b6345d6fab56a59d9b0acbd05a8526ffdb473e8174f90f88fd255d8514ca2"
            ),
            "geometryMutable": False,
            "appearanceStrategyCount": 1,
        },
        "candidatePredictionProtocol": [
            "open_only_locked_front_rear_source_bytes",
            "project_source_pixel_through_locked_camera_to_visible_candidate_triangle",
            "record_barycentric_material_uv_and_exact_source_pixel_provenance",
            "apply_bounded_source_backed_semantic_island_blend",
            "mark_remaining_active_texels_generated_and_exclude_from_source_fidelity",
            "freeze_atlas_maps_provenance_candidate_package_fallback_and_prediction_identity",
            "mount_known_evaluator_only_after_prediction_commit",
        ],
        "rendererAndEvaluatorHashes": deepcopy(protocol["frozenImplementations"]),
        "implementationFiles": records,
        "implementationBundleHash": bundle_hash,
        "evaluatorOnlyMounted": False,
        "knownTargetTrialCount": 0,
        "maximumKnownTargetTrials": 1,
        "integrity": {"implementationFreezeHash": ""},
    }
    payload = deepcopy(freeze)
    payload["integrity"]["implementationFreezeHash"] = ""
    freeze["integrity"]["implementationFreezeHash"] = sha256_bytes(
        canonical_dumps(payload).encode("utf-8")
    )
    write_canonical_json(root / IMPLEMENTATION_FREEZE_PATH, freeze)
    print(canonical_dumps(freeze))


if __name__ == "__main__":
    main()
