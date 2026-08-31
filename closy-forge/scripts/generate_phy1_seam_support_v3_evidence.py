from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path
from time import monotonic
from typing import Any

from closy_forge.binding.reconstruct import reconstruct_vertices
from closy_forge.fitting.exact_d0_candidate import inventory_digest, package_inventory
from closy_forge.geometry.glb_io import read_glb_meshset, write_indexed_glb
from closy_forge.geometry.mesh_model import MeshSet
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import geometry_content_hash, sha256_bytes, sha256_file
from closy_forge.package_io.managed_output import (
    MARKER_NAME,
    cleanup_managed_staging,
    create_managed_staging,
    publish_managed_staging,
)
from closy_forge.simulation.reference_cloth_solver import flatten_mesh, replace_mesh_positions
from closy_forge.simulation_topology_v2.phy1_seam_support_v3 import (
    evaluate_neutral_preflight,
    evidence_inventory,
    load_phy1_v3_inputs,
    refresh_research_matrix,
    run_analytic_microfixtures,
    solve_neutral_once,
)
from closy_forge.simulation_topology_v2.seam_support_v3 import (
    audit_support_inventory,
    load_experiment_lock,
)

PURPOSE = "phy1_seam_support_v3"
EVIDENCE_PATH = Path("docs/evidence/phy1_seam_support_v3")
ANALYTIC_PREFLIGHT_PATH = Path("docs/evidence/phy1_seam_support_v3_analytic_preflight.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--analytic-only", action="store_true")
    parser.add_argument("--validate-committed", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.analytic_only and args.validate_committed:
        parser.error("--analytic-only and --validate-committed are mutually exclusive")
    if args.analytic_only:
        analytic = _analytic(root)
        write_canonical_json(root / ANALYTIC_PREFLIGHT_PATH, analytic)
        print(
            f"analytic={analytic['status']} controls="
            f"{sum(item['detected'] for item in analytic['corruptionControls'])}/"
            f"{len(analytic['corruptionControls'])}"
        )
        return 0
    if args.validate_committed:
        summary = validate_committed_evidence(root)
        print(
            f"outcome={summary['outcomeClass']} evidence={summary['evidenceDigest']} "
            f"files={summary['inventoryCount']}"
        )
        return 0
    summary = generate_evidence(root)
    print(
        f"outcome={summary['outcomeClass']} evidence={summary['evidenceDigest']} "
        f"files={summary['inventoryCount']} primarySeconds={summary['primarySeconds']:.6f} "
        f"repeatSeconds={summary['repeatSeconds']:.6f} rebuildSeconds="
        f"{summary['rebuildSeconds']:.6f}"
    )
    return 0


def generate_evidence(root: Path) -> dict[str, Any]:
    allowed_root = root / EVIDENCE_PATH.parent
    target = root / EVIDENCE_PATH
    first = create_managed_staging(target, allowed_root=allowed_root, purpose=PURPOSE)
    try:
        first_summary = _build_bundle(root, first, delete_rebuild_verified=True)
        first_inventory = package_inventory(first, exclude={MARKER_NAME})
        first_digest = inventory_digest(first_inventory)
    finally:
        cleanup_managed_staging(first, allowed_root=allowed_root, purpose=PURPOSE)

    second = create_managed_staging(target, allowed_root=allowed_root, purpose=PURPOSE)
    try:
        second_summary = _build_bundle(root, second, delete_rebuild_verified=True)
        second_inventory = package_inventory(second, exclude={MARKER_NAME})
        second_digest = inventory_digest(second_inventory)
        if first_inventory != second_inventory or first_digest != second_digest:
            raise ValueError("phy1_v3_delete_rebuild_byte_mismatch")
        if first_summary["outcomeClass"] != second_summary["outcomeClass"]:
            raise ValueError("phy1_v3_delete_rebuild_outcome_mismatch")
        publish_managed_staging(
            second,
            target,
            allowed_root=allowed_root,
            purpose=PURPOSE,
            force=True,
        )
    except BaseException:
        cleanup_managed_staging(second, allowed_root=allowed_root, purpose=PURPOSE)
        raise
    return {
        **second_summary,
        "deleteRebuildDigest": second_digest,
        "rebuildSeconds": float(second_summary["primarySeconds"])
        + float(second_summary["repeatSeconds"]),
    }


def validate_committed_evidence(root: Path) -> dict[str, Any]:
    evidence_root = root / EVIDENCE_PATH
    lock = load_experiment_lock(root)
    inputs = load_phy1_v3_inputs(root, lock)
    analytic = run_analytic_microfixtures(root, lock, inputs)
    committed_analytic = _object(evidence_root / "analytic_microfixtures.json")
    if canonical_dumps(analytic) != canonical_dumps(committed_analytic):
        raise ValueError("phy1_v3_committed_analytic_mismatch")
    standalone = _object(root / ANALYTIC_PREFLIGHT_PATH)
    if canonical_dumps(analytic) != canonical_dumps(standalone):
        raise ValueError("phy1_v3_standalone_analytic_mismatch")

    neutral = _object(evidence_root / "neutral_preflight.json")
    outcome = _object(evidence_root / "outcome.json")
    matrix = _object(evidence_root / "final_d0_research_prototype_matrix_v2.json")
    trajectory = _object(evidence_root / "trajectory/index.json")
    manifest = _object(evidence_root / "evidence_manifest.json")
    _validate_integrity(neutral, "evidenceHash")
    _validate_integrity(outcome, "outcomeHash")
    _validate_integrity(matrix, "matrixHash")
    _validate_integrity(trajectory, "trajectoryIndexHash")
    _validate_integrity(manifest, "manifestHash")
    if outcome.get("outcomeClass") != "A_neutral_preflight_failed_v3":
        raise ValueError("phy1_v3_committed_outcome_not_supported")
    if _mapping(neutral.get("acceptance")).get("status") != "fail":
        raise ValueError("phy1_v3_neutral_failure_required_for_outcome_a")
    if _mapping(neutral.get("determinism")).get("deleteRebuildVerified") is not True:
        raise ValueError("phy1_v3_delete_rebuild_not_verified")
    if outcome.get("neutralEvidenceHash") != _mapping(neutral["integrity"])["evidenceHash"]:
        raise ValueError("phy1_v3_outcome_neutral_hash_mismatch")
    if matrix.get("physicalCandidateId") != neutral.get("physicalCandidateId"):
        raise ValueError("phy1_v3_matrix_identity_mismatch")

    frames = trajectory.get("frames", [])
    if not isinstance(frames, list) or not frames:
        raise ValueError("phy1_v3_trajectory_missing")
    for item in frames:
        record = _mapping(item)
        path = evidence_root / str(record["path"])
        if sha256_file(path) != record.get("sha256"):
            raise ValueError("phy1_v3_trajectory_byte_hash_mismatch")
        if geometry_content_hash(read_glb_meshset(path)) != record.get("meshContentHash"):
            raise ValueError("phy1_v3_trajectory_content_hash_mismatch")
    settled = read_glb_meshset(evidence_root / "neutral_settled_simulation.glb")
    if (
        geometry_content_hash(settled)
        != _mapping(neutral["identities"])["simulationSettledContentHash"]
    ):
        raise ValueError("phy1_v3_settled_mesh_identity_mismatch")
    source_inventory = neutral.get("sourceInventory", [])
    if not isinstance(source_inventory, list):
        raise ValueError("phy1_v3_source_inventory_invalid")
    for item in source_inventory:
        record = _mapping(item)
        if sha256_file(root / str(record["path"])) != record.get("sha256"):
            raise ValueError("phy1_v3_source_hash_mismatch")

    expected_manifest = evidence_inventory(root, evidence_root)
    if canonical_dumps(expected_manifest) != canonical_dumps(manifest):
        raise ValueError("phy1_v3_evidence_manifest_mismatch")
    inventory = manifest["inventory"]
    return {
        "outcomeClass": outcome["outcomeClass"],
        "evidenceDigest": manifest["evidenceDigest"],
        "inventoryCount": len(inventory),
    }


def _analytic(root: Path) -> dict[str, Any]:
    lock = load_experiment_lock(root)
    inputs = load_phy1_v3_inputs(root, lock)
    report = run_analytic_microfixtures(root, lock, inputs)
    if report["status"] != "pass":
        raise ValueError(f"phy1_v3_analytic_microfixtures_failed:{report['failedChecks']}")
    return report


def _build_bundle(root: Path, output: Path, *, delete_rebuild_verified: bool) -> dict[str, Any]:
    lock = load_experiment_lock(root)
    inputs = load_phy1_v3_inputs(root, lock)
    analytic = run_analytic_microfixtures(root, lock, inputs)
    if analytic["status"] != "pass":
        raise ValueError(f"phy1_v3_analytic_microfixtures_failed:{analytic['failedChecks']}")
    standalone = _object(root / ANALYTIC_PREFLIGHT_PATH)
    if canonical_dumps(analytic) != canonical_dumps(standalone):
        raise ValueError("phy1_v3_analytic_changed_after_preflight")

    primary_started = monotonic()
    primary = solve_neutral_once(lock, inputs)
    primary_seconds = monotonic() - primary_started
    repeat_started = monotonic()
    repeat = solve_neutral_once(lock, inputs)
    repeat_seconds = monotonic() - repeat_started
    neutral = evaluate_neutral_preflight(
        root,
        lock,
        inputs,
        primary,
        repeat,
        analytic,
        delete_rebuild_verified=delete_rebuild_verified,
    )
    if _mapping(neutral["acceptance"])["status"] == "pass":
        raise ValueError("phy1_v3_neutral_passed_conditional_phy1_implementation_required")

    write_canonical_json(output / "analytic_microfixtures.json", analytic)
    write_canonical_json(output / "junction_graph.json", inputs.junction_graph)
    write_canonical_json(
        output / "support_inventory.json", audit_support_inventory(inputs.supports, lock)
    )
    write_canonical_json(output / "neutral_preflight.json", neutral)
    _write_trajectory(output, primary.trajectory, primary.trajectory_hashes)
    write_indexed_glb(
        output / "neutral_settled_simulation.glb",
        primary.settled_mesh,
        "PHY1 V3 settled simulation",
        (0.55, 0.64, 0.78, 1.0),
        normalize_signed_zero=True,
    )
    render_positions = reconstruct_vertices(primary.settled_mesh, inputs.binding)
    render_mesh = replace_mesh_positions(
        inputs.render_mesh,
        render_positions,
        flatten_mesh(inputs.render_mesh).mesh_offsets,
    )
    write_indexed_glb(
        output / "neutral_settled_render.glb",
        render_mesh,
        "PHY1 V3 settled dense render",
        (0.55, 0.64, 0.78, 1.0),
        normalize_signed_zero=True,
    )
    outcome = _outcome(lock, neutral)
    matrix = refresh_research_matrix(root, neutral)
    write_canonical_json(output / "outcome.json", outcome)
    write_canonical_json(output / "final_d0_research_prototype_matrix_v2.json", matrix)
    write_canonical_json(output / "evidence_manifest.json", evidence_inventory(root, output))
    return {
        "outcomeClass": outcome["outcomeClass"],
        "evidenceDigest": _object(output / "evidence_manifest.json")["evidenceDigest"],
        "inventoryCount": len(_object(output / "evidence_manifest.json")["inventory"]),
        "primarySeconds": primary_seconds,
        "repeatSeconds": repeat_seconds,
    }


def _write_trajectory(output: Path, frames: list[MeshSet], content_hashes: list[str]) -> None:
    records: list[dict[str, Any]] = []
    for index, (frame, content_hash) in enumerate(zip(frames, content_hashes, strict=True)):
        relative = Path("trajectory") / f"frame_{index:03d}.glb"
        write_indexed_glb(
            output / relative,
            frame,
            "PHY1 V3 trajectory",
            (0.55, 0.64, 0.78, 1.0),
            normalize_signed_zero=True,
        )
        records.append(
            {
                "frameIndex": index,
                "path": relative.as_posix(),
                "sha256": sha256_file(output / relative),
                "meshContentHash": content_hash,
            }
        )
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "trajectoryVersion": "closy.phy1.seam_support_v3.neutral_trajectory.v1",
        "frameCount": len(records),
        "frames": records,
        "integrity": {"trajectoryIndexHash": ""},
    }
    document["integrity"]["trajectoryIndexHash"] = _hash_without(document, "trajectoryIndexHash")
    write_canonical_json(output / "trajectory/index.json", document)


def _outcome(lock: Mapping[str, Any], neutral: Mapping[str, Any]) -> dict[str, Any]:
    if _mapping(neutral.get("acceptance")).get("status") != "fail":
        raise ValueError("phy1_v3_outcome_a_requires_neutral_failure")
    document: dict[str, Any] = {
        "schemaVersion": 1,
        "outcomeVersion": "closy.phy1.seam_support_v3.unit_d_outcome.v1",
        "outcomeClass": "A_neutral_preflight_failed_v3",
        "physicalCandidateId": _mapping(lock["integrity"])["physicalCandidateId"],
        "neutralEvidenceHash": _mapping(neutral["integrity"])["evidenceHash"],
        "neutralFailedChecks": _mapping(neutral["acceptance"])["failedChecks"],
        "progression": {
            "physicalLaneStopped": True,
            "phy1Executed": False,
            "ccdExecuted": False,
            "z2Executed": False,
            "runtimeV1RemainsSelected": True,
            "topologyV2RemainsOptIn": True,
        },
        "budget": lock["budget"],
        "unsupportedClaims": lock["unsupportedClaims"],
        "integrity": {"outcomeHash": ""},
    }
    document["integrity"]["outcomeHash"] = _hash_without(document, "outcomeHash")
    return document


def _validate_integrity(document: Mapping[str, Any], field: str) -> None:
    if _mapping(document.get("integrity")).get(field) != _hash_without(document, field):
        raise ValueError(f"phy1_v3_integrity_mismatch:{field}")


def _hash_without(document: Mapping[str, Any], field: str) -> str:
    payload = dict(document)
    payload["integrity"] = {**_mapping(document.get("integrity")), field: ""}
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _object(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"object_required:{path.as_posix()}")
    return value


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


if __name__ == "__main__":
    raise SystemExit(main())
