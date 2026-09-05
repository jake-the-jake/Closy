"""Checkpointed exposed regression. Calling run_evaluation is an explicit final run."""

from __future__ import annotations

import ast
import math
import platform
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from closy_forge.binding.binary_format import read_binding as read_legacy_binding
from closy_forge.geometry.glb_io import read_glb_meshset, write_indexed_glb
from closy_forge.geometry.mesh_model import Mesh, MeshSet
from closy_forge.manual_provider_c3_v1.states import MOTION_STATES
from closy_forge.package_io.canonical_json import (
    read_json,
    write_canonical_json,
    write_canonical_text,
)
from closy_forge.package_io.hashing import sha256_file

from .binding import build_binding_v2, refinement_policy, write_binding_v2
from .checker import check_rest
from .package import build_package_v2, check_package_v2, digest_json

BASELINE_SOURCES = tuple(
    (f"manual-{prefix}-{index:02d}", family)
    for prefix, family in (
        ("skirt", "simple_skirt"),
        ("sleeveless", "sleeveless_top"),
        ("tshirt", "tshirt"),
    )
    for index in range(1, 4)
)
UNIT_A_FAMILIES = ("tshirt", "sleeveless_top", "simple_skirt")
OTHER_FAMILIES = (
    "long_sleeved_top",
    "simple_trousers",
    "simple_dress",
    "button_shirt",
    "jacket_outerwear",
    "layered_asymmetric",
)
EXTRA_CASES = (
    {
        "caseId": "extra-dimensions",
        "columns": 9,
        "rows": 9,
        "width": 0.42,
        "height": 0.58,
        "expected": "pass",
        "stress": "dimensions",
    },
    {
        "caseId": "extra-density",
        "columns": 17,
        "rows": 13,
        "width": 0.46,
        "height": 0.61,
        "expected": "pass",
        "stress": "sampling_density",
    },
    {
        "caseId": "extra-ordering",
        "columns": 13,
        "rows": 8,
        "width": 0.43,
        "height": 0.55,
        "expected": "pass",
        "stress": "reordered_vertices_and_faces",
    },
    {
        "caseId": "extra-seam-opening",
        "columns": 9,
        "rows": 11,
        "width": 0.48,
        "height": 0.64,
        "expected": "pass",
        "stress": "explicit_paired_sides_open_top_and_hem",
    },
    {
        "caseId": "reject-hole",
        "columns": 7,
        "rows": 9,
        "width": 0.42,
        "height": 0.58,
        "expected": "reject",
        "stress": "removed_face",
        "expectedReason": "unsupported_grid_connectivity",
    },
    {
        "caseId": "reject-offset",
        "columns": 7,
        "rows": 9,
        "width": 0.42,
        "height": 0.58,
        "expected": "reject",
        "stress": "over_budget_profile",
        "expectedReason": "residual_budget",
    },
    {
        "caseId": "reject-seam-index",
        "columns": 7,
        "rows": 9,
        "width": 0.42,
        "height": 0.58,
        "expected": "reject",
        "stress": "invalid_explicit_seam",
        "expectedReason": "seam_endpoint_invalid",
    },
)


def protocol_document(forge_root: Path) -> dict[str, Any]:
    legacy_path = forge_root / "fixtures/manual_provider_c3_v1/protocol.json"
    legacy = read_json(legacy_path)
    body = dict(legacy)
    declared_digest = body.pop("protocolDigest")
    # V1 canonical JSON did not include the shared writer's terminal newline.
    from closy_forge.manual_provider_c3_v1.common import digest_value

    if digest_value(body) != declared_digest:
        raise ValueError("evaluation_v2_legacy_protocol_digest_invalid")
    original_limits = (
        9,
        3,
        99,
        11,
        1.0,
        0.9,
        0.999,
        0,
        0.008,
        0.02,
        0.006,
        0.012,
        0,
        1.0,
        1.0,
        2097152,
        True,
    )
    gates = []
    for index, expected in enumerate(original_limits, start=1):
        gate_id = f"MPC3-{index:02d}"
        gate = dict(legacy["gates"][gate_id])
        if gate["threshold"] != expected:
            raise ValueError("evaluation_v2_legacy_limit_changed")
        gate["gateId"] = gate_id
        if gate_id == "MPC3-12":
            gate["legacyMetric"] = gate["metric"]
            gate["metric"] = "maximumUvEdgeReconstructionErrorMeters"
            gate["scope"] = "legacy_uv_extrema_reconstruction_not_physical_seam_gap"
        if gate_id == "MPC3-14":
            gate["legacyMetric"] = gate["metric"]
            gate["metric"] = "openBoundaryGeometryPreservedRate"
            gate["scope"] = (
                "actual_boundary_lengths_and_nondegenerate_motion_not_named_opening_qualification"
            )
        gates.append(gate)
    return {
        "schemaVersion": 2,
        "version": "closy.manual_provider_binding_v2.protocol.v3",
        "scope": "exposed_development_not_held_out",
        "legacyProtocolSha256": sha256_file(legacy_path),
        "baseline": [{"sourceId": s, "family": f} for s, f in BASELINE_SOURCES],
        "baselineRowCount": 99,
        "cleanBuildCount": 2,
        "retainBothBuilds": True,
        "states": [asdict(s) for s in MOTION_STATES],
        "gates": gates,
        "extraCases": [dict(c, exposed=True, usedDuringDevelopment=True) for c in EXTRA_CASES],
        "extraPositiveMotionRows": 44,
        "extraExpectedRejections": 3,
        "cageRefinement": refinement_policy(),
        "retainedDevelopmentFailures": [
            {
                "caseId": "extra-dimensions",
                "stateId": "step_left",
                "initialP95ErrorMeters": 0.007918341249059907,
                "initialMaximumErrorMeters": 0.01609645360978089,
                "packagePath": (
                    ".tmp/unit-b-package-tiny-01/test_predeclared_small_positiv0/package"
                ),
                "manifestSha256": (
                    "59e27d7ab932392c0f870f8fe440ffbd6c8f1928a6dfc3f0d670a200c8b0ded5"
                ),
                "motionManifestSha256": (
                    "16fa26dc4462fd855791ad5f06d5fe64eef7dab014d546358153dca3d921d83d"
                ),
            },
            {
                "caseId": "extra-seam-opening",
                "stateId": "step_left",
                "initialP95ErrorMeters": 0.009397788159590435,
                "initialMaximumErrorMeters": 0.016073140875199312,
                "packagePath": (
                    ".tmp/unit-b-package-tiny-01/test_predeclared_small_positiv3/package"
                ),
                "manifestSha256": (
                    "4ad9a4353bf95e99b6fc22ff2ab2646c651bcb6f1e263ca9b79eadb42b046989"
                ),
                "motionManifestSha256": (
                    "229b3b900f6f62fc79dba7af2e276cbfbc8777886eeb1222d0e4d35aa5587dd5"
                ),
            },
        ],
        "unitANominalFamiliesToProbe": list(UNIT_A_FAMILIES),
        "otherUnitAFamilies": {f: "unsupported_not_claimed" for f in OTHER_FAMILIES},
        "float32ComparisonToleranceMeters": 2e-6,
        "restLimitMeters": 0.008,
        "realPairedSeamPolicy": "measure_only_explicit_vertex_correspondence_else_not_available",
        "scientificCandidateConsumed": False,
        "heavyEvaluationAuthorizedByInvocationOnly": True,
    }


def _atomic_json(path: Path, data: Any) -> None:
    temporary = path.with_name(path.name + ".partial")
    write_canonical_json(temporary, data)
    temporary.replace(path)


def source_inventory(forge: Path) -> dict[str, Any]:
    """Hash the local static import closure, without importing or executing it."""
    src = forge / "src"
    pending = list((src / "closy_forge/manual_provider_binding_v2").glob("*.py"))
    pending.extend(
        [
            forge / "scripts/evaluate_manual_provider_binding_v2.py",
            forge / "tests/unit/test_manual_provider_binding_v2.py",
            forge / "tests/unit/test_manual_provider_binding_package_v2.py",
            src / "closy_forge/family_integration_v1/compiler.py",
        ]
    )
    # Unit A dispatches family modules dynamically; include their import closure.
    pending.extend((src / "closy_forge/garments").rglob("*.py"))
    seen: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level and path.is_relative_to(src):
                    base = path.relative_to(src).with_suffix("").parts[: -node.level]
                    modules = [".".join((*base, node.module or "")).rstrip(".")]
                elif not node.level:
                    modules = [node.module or ""]
            for module in modules:
                if not module.startswith("closy_forge"):
                    continue
                target = src.joinpath(*module.split("."))
                candidate = target.with_suffix(".py")
                pending.append(candidate if candidate.is_file() else target / "__init__.py")
                for parent in target.parents:
                    if parent == src:
                        break
                    pending.append(parent / "__init__.py")
    return {p.relative_to(forge).as_posix(): sha256_file(p) for p in sorted(seen)}


def input_inventory(source_root: Path, unit_a_root: Path) -> dict[str, Any]:
    records = []
    for source_id, family in BASELINE_SOURCES:
        root = source_root / source_id
        for relative in (
            "manifest.json",
            "render/clean.glb",
            "reports/semantics.json",
            "reports/cleanup.json",
            "reports/binding.json",
            "render/fallback.glb",
            "binding/hybrid_binding.bin",
        ):
            path = root / relative
            records.append(
                {
                    "scope": "baseline",
                    "caseId": source_id,
                    "family": family,
                    "path": relative,
                    "exists": path.is_file(),
                    "sha256": sha256_file(path) if path.is_file() else None,
                    "bytes": path.stat().st_size if path.is_file() else None,
                }
            )
    for family in UNIT_A_FAMILIES:
        root = unit_a_root / family / "nominal"
        paths = sorted(p for p in root.rglob("*") if p.is_file()) if root.is_dir() else []
        if not paths:
            records.append({"scope": "unit_a", "caseId": family, "exists": False})
        records.extend(
            {
                "scope": "unit_a",
                "caseId": family,
                "path": p.relative_to(root).as_posix(),
                "exists": True,
                "sha256": sha256_file(p),
                "bytes": p.stat().st_size,
            }
            for p in paths
        )
    return {
        "sourceRoot": str(source_root.resolve()),
        "unitARoot": str(unit_a_root.resolve()),
        "files": records,
    }


def legacy_rest_witness(source: Path) -> dict[str, Any]:
    clean = read_glb_meshset(source / "render/clean.glb")
    cage = read_glb_meshset(source / "render/fallback.glb")
    binding = read_legacy_binding(source / "binding/hybrid_binding.bin")
    triangles = [tuple(m.vertices[i] for i in tri) for m in cage.meshes for tri in m.triangles]
    rows: list[dict[str, Any]] = []
    index = 0
    for mesh in clean.meshes:
        for local, target in enumerate(mesh.vertices):
            record = binding.records[index]
            points = triangles[record.simulation_triangle_index]
            weights = (
                1 - record.barycentric_u - record.barycentric_v,
                record.barycentric_u,
                record.barycentric_v,
            )
            position = tuple(sum(weights[j] * points[j][k] for j in range(3)) for k in range(3))
            rows.append(
                {
                    "errorMeters": math.dist(target, position),
                    "panelId": mesh.panel_id,
                    "localVertexIndex": local,
                    "globalVertexIndex": index,
                    "uv": mesh.panel_uvs[local],
                    "residualMeters": [target[k] - position[k] for k in range(3)],
                }
            )
            index += 1
    errors = sorted(r["errorMeters"] for r in rows)
    return {
        "maximumErrorMeters": errors[-1],
        "p95ErrorMeters": errors[math.ceil(0.95 * len(errors)) - 1],
        "worst": max(rows, key=lambda r: r["errorMeters"]),
        "scope": "read_only_saved_V1_bytes_no_evaluator_rerun",
    }


def verify_saved_source(source: Path, family: str) -> dict[str, Any]:
    from closy_forge.manual_provider_c3_v1.common import digest_value

    manifest: dict[str, Any] = read_json(source / "manifest.json")
    body = dict(manifest)
    digest = body.pop("packageDigest", None)
    if manifest.get("family") != family or digest_value(body) != digest:
        raise ValueError("evaluation_v2_saved_source_identity_invalid")
    if digest_value(manifest["inventory"]) != manifest["inventoryDigest"]:
        raise ValueError("evaluation_v2_saved_source_inventory_invalid")
    inventory = {row["path"]: row for row in manifest["inventory"]}
    for name in (
        "render/clean.glb",
        "reports/semantics.json",
        "reports/cleanup.json",
        "reports/binding.json",
        "render/fallback.glb",
        "binding/hybrid_binding.bin",
    ):
        path = source / name
        if (
            name not in inventory
            or path.stat().st_size != inventory[name]["bytes"]
            or (sha256_file(path) != inventory[name]["sha256"])
        ):
            raise ValueError(f"evaluation_v2_saved_source_file_mismatch:{name}")
    return manifest


def write_extra_input(case: dict[str, Any], root: Path) -> tuple[Path, Path]:
    """Predeclared small authored two-panel shell fixtures, never canonical garments."""
    root.mkdir(parents=True, exist_ok=False)
    columns, rows = case["columns"], case["rows"]
    meshes = []
    pairs: list[dict[str, Any]] = []
    for side in range(2):
        vertices, uvs, triangles = [], [], []
        for r in range(rows):
            v = r / (rows - 1)
            width = case["width"] * (1 + 0.08 * v) + (0.012 if r == 3 else 0)
            if case["caseId"] == "reject-offset" and r == 3:
                width += 0.20
            for c in range(columns):
                u = c / (columns - 1)
                x = (u - 0.5) * width
                vertices.append(
                    (
                        x,
                        0.7 + case["height"] * v,
                        (1 if side == 0 else -1) * 0.025 * math.sin(math.pi * u),
                    )
                )
                uvs.append((u, v))
        for r in range(rows - 1):
            for c in range(columns - 1):
                a = r * columns + c
                b, d, e = a + 1, a + columns, a + columns + 1
                cell = [(a, b, d), (b, e, d)] if (r + c) % 2 else [(a, b, e), (a, e, d)]
                triangles.extend(cell if not side else [(x, z, y) for x, y, z in cell])
        if case["caseId"] == "reject-hole":
            triangles.pop()
        if case["caseId"] == "extra-ordering":
            n = len(vertices)
            vertices, uvs = vertices[::-1], uvs[::-1]
            triangles = [(n - 1 - a, n - 1 - b, n - 1 - c) for a, b, c in triangles[::-1]]
        meshes.append(
            Mesh(f"development-part-{side}", f"layer.part.{side}", vertices, uvs, triangles)
        )
    if case["caseId"] in ("extra-seam-opening", "reject-seam-index"):
        for row in range(rows):
            for column in (0, columns - 1):
                index = row * columns + column
                pairs.append(
                    {
                        "seamId": f"side.{column}",
                        "a": {"panelId": "layer.part.0", "vertexIndex": index},
                        "b": {"panelId": "layer.part.1", "vertexIndex": index},
                    }
                )
        if case["caseId"] == "reject-seam-index":
            pairs[0]["b"]["vertexIndex"] = columns * rows
    openings = ["opening.hem", "opening.top"]
    document = {
        "schemaVersion": 2,
        "status": "pass",
        "openingIds": openings,
        "seamPairs": pairs,
        "fixtureScope": "exposed_authored_shell_not_cloth_ground_truth",
        "labels": [
            {"semanticId": label, "status": "accepted", "confidence": 1.0}
            for label in [*(m.panel_id for m in meshes), *openings]
        ],
    }
    clean_path, semantics_path = root / "clean.glb", root / "semantics.json"
    write_indexed_glb(
        clean_path,
        MeshSet(meshes),
        "exposed-extra-shell",
        (0.3, 0.5, 0.4, 1.0),
        normalize_signed_zero=True,
    )
    write_canonical_json(semantics_path, document)
    return clean_path, semantics_path


def failed_rows(source_id: str, family: str, reason: str) -> list[dict[str, Any]]:
    return [
        {
            "sourceId": source_id,
            "family": family,
            "stateId": s.state_id,
            "status": "fail",
            "error": reason,
            "packageDigest": None,
            "metricsAvailable": False,
        }
        for s in MOTION_STATES
    ]


def _baseline_metrics(packages: list[dict[str, Any]], deterministic: bool) -> dict[str, Any]:
    successes = [p for p in packages if "package" in p]
    outputs = [p["package"] for p in successes]
    rows = [r for p in packages for r in p["rows"]]
    complete = len(outputs) == 9 and all(len(p["rows"]) == 11 for p in outputs)

    def maximum(key: str) -> float | None:
        return max((float(r[key]) for r in rows), default=0) if complete else None

    return {
        "sourceCount": len(packages),
        "familyCount": len({p["family"] for p in packages}),
        "evaluationRowCount": len(rows),
        "motionStateCount": len({r["stateId"] for r in rows}),
        "cleanTopologyPassRate": sum(bool(p["geometryValid"]) for p in outputs) / 9,
        "minimumSemanticConfidence": min(
            (p["semantics"]["minimumAcceptedConfidence"] for p in outputs), default=0
        )
        if complete
        else None,
        "minimumBindingCoverage": min((p["binding"]["coverage"] for p in outputs), default=0)
        if complete
        else None,
        "maximumOutOfDomainCount": max(
            (p["binding"]["outOfDomainCount"] for p in outputs), default=0
        )
        if complete
        else None,
        "maximumRestErrorMeters": max(
            (p["rest"]["restMaximumErrorMeters"] for p in outputs), default=0
        )
        if complete
        else None,
        "maximumP95RestErrorMeters": max(
            (p["rest"]["restP95ErrorMeters"] for p in outputs), default=0
        )
        if complete
        else None,
        "maximumMotionErrorMeters": maximum("maximumErrorMeters"),
        "maximumP95MotionErrorMeters": maximum("p95ErrorMeters"),
        "maximumUvEdgeReconstructionErrorMeters": maximum("maximumUvEdgeReconstructionErrorMeters"),
        "totalInvertedTriangleCount": sum(r["invertedTriangleCount"] for r in rows)
        if complete
        else None,
        "totalCollapsedTriangleCount": sum(r["collapsedTriangleCount"] for r in rows)
        if complete
        else None,
        "openBoundaryGeometryPreservedRate": sum(
            r.get("boundaryGeometry", {}).get("preserved", False) for r in rows
        )
        / 99,
        "vec4TangentPackageRate": sum(
            all(g["attributes"]["hasVec4Tangents"] for g in p["geometry"].values()) for p in outputs
        )
        / 9,
        "maximumPackageBytes": max((p["packageBytes"] for p in outputs), default=0)
        if complete
        else None,
        "deterministicTwoBuilds": deterministic,
    }


def derive_gates(protocol: dict[str, Any], metrics: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for definition in protocol["gates"]:
        value = metrics[definition["metric"]]
        passed = value is not None and (
            value >= definition["threshold"]
            if definition["operator"] == ">="
            else value <= definition["threshold"]
            if definition["operator"] == "<="
            else value == definition["threshold"]
        )
        rows.append({**definition, "observed": value, "status": "pass" if passed else "fail"})
    return rows


def probe_unit_a(unit_a_root: Path, output_root: Path, family: str) -> dict[str, Any]:
    from closy_forge.family_integration_v1.compiler import validate_family

    root = unit_a_root / family / "nominal"
    if not root.is_dir():
        return {"family": family, "status": "not_run", "reason": "unit_a_nominal_not_available"}
    validated = validate_family(root)
    clean_path = root / "render/fallback.glb"
    render = read_glb_meshset(clean_path)
    record = {
        "family": family,
        "unitAPackageIdentity": validated["packageIdentity"],
        "inputCleanSha256": sha256_file(clean_path),
        "renderVertexCount": render.vertex_count,
        "scope": "saved_Unit_A_nominal_API_probe_no_recompile",
    }
    try:
        bound = build_binding_v2(render)
    except ValueError as exc:
        return {**record, "status": "unsupported", "reason": str(exc), "fullC3Claim": False}
    output_root.mkdir(parents=True, exist_ok=False)
    cage, binding = output_root / "cage.glb", output_root / "local_frame_v2.bin"
    write_indexed_glb(
        cage, bound.cage, "unit-a-binding-probe", (0.3, 0.5, 0.4, 1.0), normalize_signed_zero=True
    )
    write_binding_v2(binding, bound.binding)
    rest = check_rest(cage, clean_path, binding, bound.report)
    return {**record, "status": rest["status"], "rest": rest, "fullC3Claim": False}


def run_evaluation(
    output_root: Path,
    *,
    source_root: Path,
    unit_a_root: Path,
    forge_root: Path,
    resume: bool = False,
) -> dict[str, Any]:
    """Execute only on explicit invocation; checkpoint each attempted source/repeat.

    Resume requires unchanged code/input/protocol hashes. Completed attempts,
    including failures, are never retried; interrupted partial attempts are kept
    as failures at their original denominator. Both deterministic builds remain.
    """
    protocol = protocol_document(forge_root)
    sources, inputs = source_inventory(forge_root), input_inventory(source_root, unit_a_root)
    identities = {
        "protocolDigest": digest_json(protocol),
        "sourceDigest": digest_json(sources),
        "inputDigest": digest_json(inputs),
    }
    if resume:
        checkpoint = read_json(output_root / "checkpoint.json")
        if checkpoint["identities"] != identities:
            raise ValueError("evaluation_v2_resume_identity_mismatch")
        if (output_root / "result.json").is_file():
            saved: dict[str, Any] = read_json(output_root / "result.json")
            unhashed = dict(saved)
            if unhashed.pop("resultDigest", None) != digest_json(unhashed):
                raise ValueError("evaluation_v2_saved_result_digest_mismatch")
            for attempt in saved["packageAttempts"]:
                if "package" in attempt:
                    verified = check_package_v2(
                        output_root / f"build{attempt['repeat']}" / attempt["sourceId"]
                    )
                    if verified["packageDigest"] != attempt["package"]["packageDigest"]:
                        raise ValueError("evaluation_v2_saved_package_digest_mismatch")
            return saved
    else:
        if output_root.exists():
            raise ValueError("evaluation_v2_output_must_be_fresh")
        output_root.mkdir(parents=True)
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=forge_root, text=True
        ).strip()
        _atomic_json(output_root / "protocol.json", protocol)
        _atomic_json(
            output_root / "source_inventory.json",
            {"head": head, "files": sources, "digest": identities["sourceDigest"]},
        )
        _atomic_json(
            output_root / "input_inventory.json", {**inputs, "digest": identities["inputDigest"]}
        )
        checkpoint = {
            "identities": identities,
            "attempts": [],
            "extras": [],
            "unitA": [],
            "active": None,
        }
        _atomic_json(output_root / "checkpoint.json", checkpoint)
    attempts = checkpoint["attempts"]
    if checkpoint["active"] is not None:
        active = checkpoint["active"]
        if active["scope"] == "baseline":
            reason = "interrupted_partial_attempt_retained_not_retried"
            attempts.append(
                {
                    **active,
                    "status": "fail",
                    "error": reason,
                    "rows": failed_rows(active["sourceId"], active["family"], reason),
                }
            )
        elif active["scope"] == "extra":
            checkpoint["extras"].append(
                {
                    **active,
                    "status": "fail",
                    "error": "interrupted_partial_extra_retained",
                    "rows": []
                    if active["expected"] == "reject"
                    else failed_rows(
                        active["caseId"],
                        "development_two_panel_shell",
                        "interrupted_partial_extra_retained",
                    ),
                }
            )
        else:
            checkpoint["unitA"].append(
                {**active, "status": "fail", "reason": "interrupted_partial_unit_a_probe_retained"}
            )
        checkpoint["active"] = None
        _atomic_json(output_root / "checkpoint.json", checkpoint)
    started, cpu_started = time.perf_counter(), time.process_time()
    for repeat in (1, 2):
        for source_id, family in BASELINE_SOURCES:
            if any(p["repeat"] == repeat and p["sourceId"] == source_id for p in attempts):
                continue
            active = {
                "scope": "baseline",
                "repeat": repeat,
                "sourceId": source_id,
                "family": family,
            }
            checkpoint["active"] = active
            _atomic_json(output_root / "checkpoint.json", checkpoint)
            begin = time.perf_counter()
            root = source_root / source_id
            try:
                source_manifest = verify_saved_source(root, family)
                package = build_package_v2(
                    root / "render/clean.glb",
                    root / "reports/semantics.json",
                    output_root / f"build{repeat}" / source_id,
                    source_id=source_id,
                    family=family,
                    source_identity={
                        "legacyPackageDigest": source_manifest["packageDigest"],
                        "legacyManifestSha256": sha256_file(root / "manifest.json"),
                    },
                )
                row = {
                    **active,
                    "status": package["status"],
                    "package": package,
                    "rows": [
                        {**r, "packageDigest": package["packageDigest"]} for r in package["rows"]
                    ],
                    "oldRest": legacy_rest_witness(root),
                }
            except Exception as exc:
                reason = f"{type(exc).__name__}:{exc}"
                row = {
                    **active,
                    "status": "fail",
                    "error": reason,
                    "rows": failed_rows(source_id, family, reason),
                }
            row["wallSeconds"] = time.perf_counter() - begin
            attempts.append(row)
            checkpoint["active"] = None
            _atomic_json(output_root / "checkpoint.json", checkpoint)
            print(
                f"baseline {len(attempts)}/18 {source_id} build{repeat} {row['status']}", flush=True
            )
    for case in protocol["extraCases"]:
        if any(r["caseId"] == case["caseId"] for r in checkpoint["extras"]):
            continue
        checkpoint["active"] = {"scope": "extra", **case}
        _atomic_json(output_root / "checkpoint.json", checkpoint)
        try:
            clean, semantic = write_extra_input(case, output_root / "extra_inputs" / case["caseId"])
            checkpoint["active"]["inputHashes"] = {
                "cleanSha256": sha256_file(clean),
                "semanticsSha256": sha256_file(semantic),
            }
            _atomic_json(output_root / "checkpoint.json", checkpoint)
            package = build_package_v2(
                clean,
                semantic,
                output_root / "extra_packages" / case["caseId"],
                source_id=case["caseId"],
                family="development_two_panel_shell",
                source_identity={"fixtureDefinitionDigest": digest_json(case)},
            )
            passed = case["expected"] == "pass" and package["status"] == "pass"
            result = {
                **case,
                "status": "pass" if passed else "fail",
                "outcome": "built",
                "package": package,
                "rows": [{**r, "packageDigest": package["packageDigest"]} for r in package["rows"]],
            }
        except Exception as exc:
            reason = f"{type(exc).__name__}:{exc}"
            passed = (
                case["expected"] == "reject"
                and isinstance(exc, ValueError)
                and case["expectedReason"] in str(exc)
            )
            result = {
                **case,
                "status": "pass" if passed else "fail",
                "outcome": "rejected",
                "reason": reason,
                "rows": []
                if case["expected"] == "reject"
                else failed_rows(case["caseId"], "development_two_panel_shell", reason),
            }
        checkpoint["extras"].append(result)
        checkpoint["active"] = None
        _atomic_json(output_root / "checkpoint.json", checkpoint)
        print(f"extra {case['caseId']} {result['status']}", flush=True)
    for family in UNIT_A_FAMILIES:
        if any(r["family"] == family for r in checkpoint["unitA"]):
            continue
        checkpoint["active"] = {"scope": "unit_a", "family": family}
        _atomic_json(output_root / "checkpoint.json", checkpoint)
        try:
            result = probe_unit_a(unit_a_root, output_root / "unit_a" / family, family)
        except Exception as exc:
            result = {"family": family, "status": "fail", "reason": f"{type(exc).__name__}:{exc}"}
        checkpoint["unitA"].append(result)
        checkpoint["active"] = None
        _atomic_json(output_root / "checkpoint.json", checkpoint)
    first = sorted((p for p in attempts if p["repeat"] == 1), key=lambda p: p["sourceId"])
    second = sorted((p for p in attempts if p["repeat"] == 2), key=lambda p: p["sourceId"])
    deterministic = len(first) == len(second) == 9 and all(
        a.get("package", {}).get("packageDigest") is not None
        and a["package"]["packageDigest"] == b.get("package", {}).get("packageDigest")
        for a, b in zip(first, second, strict=True)
    )
    metrics = _baseline_metrics(first, deterministic)
    gates = derive_gates(protocol, metrics)
    fresh = sources == source_inventory(forge_root) and inputs == input_inventory(
        source_root, unit_a_root
    )
    baseline_ok = all(g["status"] == "pass" for g in gates) and all(
        p["status"] == "pass" for p in first
    )
    extra_ok = len(checkpoint["extras"]) == len(EXTRA_CASES) and all(
        r["status"] == "pass" for r in checkpoint["extras"]
    )
    unit_a_ok = all(r["status"] in ("pass", "unsupported") for r in checkpoint["unitA"])
    rows = [r for p in first for r in p["rows"]]
    result = {
        "schemaVersion": 2,
        "version": "closy.manual_provider_binding_v2.result.v2",
        "scope": "manual_provider_binding_v2_development",
        **identities,
        "status": "pass" if baseline_ok and extra_ok and unit_a_ok and fresh else "fail",
        "baselineStatus": "pass" if baseline_ok else "fail",
        "sourceAndInputsUnchanged": fresh,
        "baselineRowDenominator": 99,
        "baselineRows": rows,
        "metrics": metrics,
        "gates": gates,
        "baselinePassedRows": sum(r["status"] == "pass" for r in rows),
        "baselineFailedRows": sum(r["status"] != "pass" for r in rows),
        "packageAttempts": attempts,
        "extras": checkpoint["extras"],
        "extraCaseDenominator": len(EXTRA_CASES),
        "extraPassedCases": sum(r["status"] == "pass" for r in checkpoint["extras"]),
        "extraFailedCases": sum(r["status"] != "pass" for r in checkpoint["extras"]),
        "extraPositiveRowDenominator": 44,
        "extraPositiveRows": [
            row for r in checkpoint["extras"] if r["expected"] == "pass" for row in r["rows"]
        ],
        "unitACompatibility": checkpoint["unitA"],
        "otherFamilies": protocol["otherUnitAFamilies"],
        "host": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "wallSecondsThisInvocation": time.perf_counter() - started,
            "cpuSecondsThisInvocation": time.process_time() - cpu_started,
            "peakResidentMemoryBytes": None,
            "residentMemoryMeasurementStatus": "not_run",
        },
        "limitsUnchanged": True,
        "scientificQualification": False,
        "globalC3Complete": False,
        "physicalMobileLatency": "not_run",
        "physicalMobileMemory": "not_run",
        "limitations": [
            "saved public shells are exposed development inputs, not held-out or physical evidence",
            "UV-edge error is not a physical seam gap",
            "named opening geometry is unlocalized without explicit vertex mapping",
            "Unit A non-grid surfaces remain unsupported rather than remeshed into a false C3 pass",
        ],
    }
    result["resultDigest"] = digest_json(result)
    _atomic_json(output_root / "result.json", result)
    _atomic_json(output_root / "baseline_rows.json", rows)
    write_canonical_text(output_root / "report.md", _report(result))
    return result


def _report(result: dict[str, Any]) -> str:
    metrics = result["metrics"]
    lines = [
        "# Manual provider binding V2 development",
        "",
        f"Status: **{result['status']}**. Baseline: {result['baselinePassedRows']}/99 rows pass; "
        f"{result['baselineFailedRows']} fail. This is exposed development only.",
        "",
        f"Rest max: {metrics['maximumRestErrorMeters']} m; maximum per-shell P95: "
        f"{metrics['maximumP95RestErrorMeters']} m.",
        f"Motion max: {metrics['maximumMotionErrorMeters']} m; P95 max: "
        f"{metrics['maximumP95MotionErrorMeters']} m.",
        f"UV-edge max: {metrics['maximumUvEdgeReconstructionErrorMeters']} m "
        "(not physical seam gap).",
        "",
        "| Source | Build 1 | Old rest max m | New rest max m |",
        "|---|---|---:|---:|",
    ]
    for p in result["packageAttempts"]:
        if p["repeat"] == 1:
            old = p.get("oldRest", {}).get("maximumErrorMeters", "unavailable")
            new = p.get("package", {}).get("rest", {}).get("restMaximumErrorMeters", "unavailable")
            lines.append(f"| {p['sourceId']} | {p['status']} | {old} | {new} |")
    lines.extend(["", "## Separate Extra Cases", ""])
    lines.extend(
        f"- {r['caseId']}: {r['status']} ({r.get('outcome', 'interrupted')})."
        for r in result["extras"]
    )
    lines.extend(["", "## Unit A Compatibility", ""])
    lines.extend(
        f"- {r['family']}: {r['status']}; {r.get('reason', 'serialized rest checked')}."
        for r in result["unitACompatibility"]
    )
    lines.extend(
        [
            "",
            "Other families are unsupported/not claimed. No global C3, canonical promotion, "
            "physical fabric, mobile, or scientific qualification follows.",
        ]
    )
    return "\n".join(lines)
