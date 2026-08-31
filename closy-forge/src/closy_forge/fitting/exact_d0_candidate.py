from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from closy_forge.appearance.bitmap_atlas import BitmapAtlasBundle
from closy_forge.avatar.reference_avatar import (
    avatar_contract,
    build_collision_mesh,
    build_reference_avatar_mesh,
)
from closy_forge.binding.binary_format import BindingFile, write_binding
from closy_forge.garments.tshirt.assembly import TRANSFORMS
from closy_forge.garments.tshirt.parameters import TShirtParameters
from closy_forge.garments.tshirt.pattern_generator import build_tshirt_pattern
from closy_forge.geometry.glb_io import read_glb_meshset, write_indexed_glb
from closy_forge.geometry.mesh_model import MeshSet, finite_mesh
from closy_forge.inspection.cpu_raster import rasterize_settled_garment
from closy_forge.inspection.source_render_fidelity import (
    _atlas_sampler,
    compare_decoded_source_and_render,
)
from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.hashing import (
    geometry_content_hash,
    sha256_bytes,
    sha256_file,
    topology_hash,
)
from closy_forge.raster import decode_png_rgba, encode_png_rgba
from closy_forge.simulation.material_physics import (
    build_material_preset_registry,
    solver_material_payload,
)
from closy_forge.simulation.reference_cloth_solver import settle_reference_cloth
from closy_forge.simulation_topology_v2 import (
    build_panel_meshes_v2,
    build_seam_constraints_v2,
    build_topology_v2_render_binding,
)

EXACT_D0_CANDIDATE_COMPILER_VERSION = "closy.exact_d0.canonical_candidate.topology_v2.v1"


@dataclass(frozen=True)
class CompiledExactCandidate:
    report: dict[str, Any]
    pattern: dict[str, Any]
    constraints: dict[str, Any]
    rest_mesh: MeshSet
    settled_mesh: MeshSet
    render_mesh: MeshSet
    binding: BindingFile
    topology_manifest: dict[str, Any]
    seam_audit: dict[str, Any]
    binding_manifest: dict[str, Any]
    binding_audit: dict[str, Any]
    rendered_views: dict[str, bytes]


def compile_exact_d0_candidate(
    *,
    contender_id: str,
    parameters: TShirtParameters,
    visual_observations: Mapping[str, Any],
    fixture_root: Path,
    fixture_manifest: Mapping[str, Any],
    atlas: BitmapAtlasBundle,
) -> CompiledExactCandidate:
    parameters.validate()
    pattern = build_tshirt_pattern(parameters)
    rest_mesh, edge_maps, topology_manifest = build_panel_meshes_v2(pattern, TRANSFORMS)
    constraints, seam_audit = build_seam_constraints_v2(pattern, edge_maps, rest_mesh)
    avatar_mesh = build_reference_avatar_mesh()
    collision_mesh = build_collision_mesh()
    avatar = avatar_contract(avatar_mesh, collision_mesh)
    descriptor = next(
        item
        for item in build_material_preset_registry()["presets"]
        if item["presetId"] == "material.cotton_jersey_d0_v1"
    )
    settle = settle_reference_cloth(
        rest_mesh,
        constraints,
        avatar,
        solver_material_payload(descriptor),
        canonical_position_digits=9,
    )
    render_mesh, _seeds, binding, binding_manifest, binding_audit = (
        build_topology_v2_render_binding(settle.settled_mesh)
    )
    fixture_by_label = {
        str(item.get("label", "")): item
        for item in _list_of_mappings(fixture_manifest.get("fixtures"))
        if item.get("role") in {"front", "rear"}
    }
    view_reports: list[dict[str, Any]] = []
    rendered_views: dict[str, bytes] = {}
    for view in _list_of_mappings(visual_observations.get("views")):
        label = str(view.get("label", ""))
        fixture = fixture_by_label.get(label)
        if fixture is None:
            raise ValueError(f"exact_d0_candidate_source_missing:{label}")
        source_path = fixture_root / str(fixture.get("relativePath", ""))
        source_payload = source_path.read_bytes()
        if sha256_bytes(source_payload) != fixture.get("expectedSha256"):
            raise ValueError("exact_d0_candidate_source_hash_mismatch")
        source = decode_png_rgba(source_payload)
        rendered = rasterize_settled_garment(
            settle.settled_mesh,
            label=label,
            width=source.width,
            height=source.height,
            camera=_mapping(view.get("camera")),
            texture_sampler=_atlas_sampler(atlas.decoded_atlas, label),
        )
        rendered_payload = encode_png_rgba(rendered.width, rendered.height, rendered.rgba)
        rendered_views[label] = rendered_payload
        metrics = compare_decoded_source_and_render(
            source,
            decode_png_rgba(rendered_payload),
        )
        view_reports.append(
            {
                "viewId": str(view.get("viewId", "")),
                "label": label,
                "sourceSha256": sha256_bytes(source_payload),
                "camera": rendered.camera,
                "renderSha256": sha256_bytes(rendered_payload),
                "renderedTriangleCount": rendered.rendered_triangle_count,
                "renderedForegroundPixels": len(rendered.foreground),
                "metrics": metrics,
            }
        )
    diagnostics = settle.diagnostics
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "compilerVersion": EXACT_D0_CANDIDATE_COMPILER_VERSION,
        "contenderId": contender_id,
        "parameters": parameters.to_json(),
        "pattern": {
            "hash": _hash(pattern),
            "panelCount": len(pattern.get("panels", [])),
            "seamCount": len(pattern.get("seams", [])),
            "openingCount": len(pattern.get("openings", [])),
        },
        "simulation": {
            "topologyAlgorithm": topology_manifest.get("simulationTopologyVersion"),
            "freshFromFittedPattern": True,
            "historicalPr39CoordinatesUsed": False,
            "restTopologyHash": topology_hash(rest_mesh),
            "restContentHash": geometry_content_hash(rest_mesh),
            "settledTopologyHash": topology_hash(settle.settled_mesh),
            "settledContentHash": geometry_content_hash(settle.settled_mesh),
            "finiteRestMesh": finite_mesh(rest_mesh),
            "finiteSettledMesh": finite_mesh(settle.settled_mesh),
            "vertexCount": rest_mesh.vertex_count,
            "triangleCount": rest_mesh.triangle_count,
            "constraintCount": len(constraints.get("constraints", [])),
            "solverExecuted": True,
            "convergenceState": diagnostics.get("convergenceState"),
            "maximumBodyPenetrationMeters": diagnostics.get("maximumBodyPenetrationMeters"),
            "maximumSeamResidualMeters": diagnostics.get("maximumSeamResidualMeters"),
            "nonFiniteValueCount": diagnostics.get("nonFiniteValueCount"),
        },
        "binding": {
            "renderTopologyHash": topology_hash(render_mesh),
            "renderContentHash": geometry_content_hash(render_mesh),
            "recordCount": len(binding.records),
            "status": binding_audit.get("status"),
            "maximumReconstructionErrorMeters": binding_audit.get(
                "maximumReconstructionErrorMeters"
            ),
        },
        "seams": {
            "status": seam_audit.get("status"),
            "constraintCount": seam_audit.get("constraintCount"),
            "multiwayEquivalenceClassCount": seam_audit.get("multiwayEquivalenceClassCount"),
        },
        "inSampleSourceRerender": {
            "classification": "front_rear_in_sample_reconstruction_not_held_out",
            "viewComparisons": view_reports,
            "aggregate": _aggregate_views(view_reports),
            "renderer": "closy_independent_cpu_triangle_raster_v1",
            "sourceFixtureGeneratorReused": False,
        },
        "atlas": {
            "reportHash": atlas.report["integrity"]["bitmapPbrReportHash"],
            "sourceObservedFraction": atlas.report["coverage"]["sourceObservedFraction"],
            "generatedControlledFillFraction": atlas.report["coverage"][
                "generatedControlledFillFraction"
            ],
            "evaluatorOnlyViewUsed": False,
        },
        "qualification": {
            "canonicalCompilerExecuted": True,
            "neutralSimulationExecuted": True,
            "independentFrontRearRerenderExecuted": True,
            "strictC3PoseSuite": "pending_evaluator_stage",
            "reference3dComparison": "pending_evaluator_stage",
            "productAcceptance": False,
        },
        "integrity": {"compiledCandidateHash": ""},
    }
    report["integrity"]["compiledCandidateHash"] = _hash(report, "compiledCandidateHash")
    return CompiledExactCandidate(
        report=report,
        pattern=pattern,
        constraints=constraints,
        rest_mesh=rest_mesh,
        settled_mesh=settle.settled_mesh,
        render_mesh=render_mesh,
        binding=binding,
        topology_manifest=topology_manifest,
        seam_audit=seam_audit,
        binding_manifest=binding_manifest,
        binding_audit=binding_audit,
        rendered_views=rendered_views,
    )


def write_compiled_exact_candidate(target: Path, candidate: CompiledExactCandidate) -> None:
    target.mkdir(parents=True, exist_ok=True)
    write_canonical_json(target / "pattern" / "pattern.json", candidate.pattern)
    write_canonical_json(target / "simulation" / "constraints.json", candidate.constraints)
    write_canonical_json(
        target / "simulation" / "topology_manifest.json", candidate.topology_manifest
    )
    write_canonical_json(target / "simulation" / "seam_audit.json", candidate.seam_audit)
    write_canonical_json(target / "binding" / "binding_manifest.json", candidate.binding_manifest)
    write_canonical_json(target / "binding" / "binding_audit.json", candidate.binding_audit)
    write_indexed_glb(
        target / "simulation" / "rest_mesh.glb",
        candidate.rest_mesh,
        "closy_exact_d0_topology_v2_rest",
        (0.15, 0.35, 0.82, 1.0),
    )
    write_indexed_glb(
        target / "simulation" / "settled_mesh.glb",
        candidate.settled_mesh,
        "closy_exact_d0_topology_v2_settled",
        (0.15, 0.35, 0.82, 1.0),
    )
    write_indexed_glb(
        target / "render" / "render_mesh.glb",
        candidate.render_mesh,
        "closy_exact_d0_topology_v2_render",
        (0.15, 0.35, 0.82, 1.0),
    )
    write_binding(target / "binding" / "sim_to_render.bin", candidate.binding)
    for label, payload in candidate.rendered_views.items():
        _write_bytes(target / "reports" / "renders" / f"{label}.png", payload)
    persisted_rest = read_glb_meshset(target / "simulation" / "rest_mesh.glb")
    persisted_settled = read_glb_meshset(target / "simulation" / "settled_mesh.glb")
    persisted_render = read_glb_meshset(target / "render" / "render_mesh.glb")
    candidate.report["simulation"]["restContentHash"] = geometry_content_hash(persisted_rest)
    candidate.report["simulation"]["settledContentHash"] = geometry_content_hash(persisted_settled)
    candidate.report["binding"]["renderContentHash"] = geometry_content_hash(persisted_render)
    candidate.report["integrity"]["compiledCandidateHash"] = _hash(
        candidate.report, "compiledCandidateHash"
    )
    write_canonical_json(target / "reports" / "compiled_candidate.json", candidate.report)


def validate_compiled_candidate_files(target: Path, report: Mapping[str, Any]) -> dict[str, Any]:
    rest = read_glb_meshset(target / "simulation" / "rest_mesh.glb")
    settled = read_glb_meshset(target / "simulation" / "settled_mesh.glb")
    render = read_glb_meshset(target / "render" / "render_mesh.glb")
    simulation = _mapping(report.get("simulation"))
    binding = _mapping(report.get("binding"))
    checks = {
        "restTopology": topology_hash(rest) == simulation.get("restTopologyHash"),
        "restContent": geometry_content_hash(rest) == simulation.get("restContentHash"),
        "settledTopology": topology_hash(settled) == simulation.get("settledTopologyHash"),
        "settledContent": geometry_content_hash(settled) == simulation.get("settledContentHash"),
        "renderTopology": topology_hash(render) == binding.get("renderTopologyHash"),
        "renderContent": geometry_content_hash(render) == binding.get("renderContentHash"),
        "finite": finite_mesh(rest) and finite_mesh(settled) and finite_mesh(render),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {"status": "pass" if not failed else "fail", "checks": checks, "failed": failed}


def package_inventory(root: Path, *, exclude: set[str] | None = None) -> list[dict[str, Any]]:
    ignored = exclude or set()
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
            "byteLength": path.stat().st_size,
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.relative_to(root).as_posix() not in ignored
    ]


def inventory_digest(inventory: list[dict[str, Any]]) -> str:
    return sha256_bytes(canonical_dumps(inventory).encode("utf-8"))


def _aggregate_views(records: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = [_mapping(record.get("metrics")) for record in records]
    front = next(record for record in records if record["label"] == "front")
    rear = next(record for record in records if record["label"] == "back")
    return {
        "viewCount": len(records),
        "meanSilhouetteIoU": _round_mean(metrics, "silhouetteIoU"),
        "maximumBoundaryChamferNormalised": max(
            float(item.get("boundaryChamferNormalised", math.inf)) for item in metrics
        ),
        "meanForegroundLinearSrgbMae": _round_mean(metrics, "foregroundLinearSrgbMae"),
        "frontRearSilhouetteDelta": round(
            abs(
                float(_mapping(front["metrics"]).get("silhouetteIoU", 0.0))
                - float(_mapping(rear["metrics"]).get("silhouetteIoU", 0.0))
            ),
            6,
        ),
        "allViewsNonBlank": all(not bool(item.get("blankOrTransparent", True)) for item in metrics),
    }


def _round_mean(items: list[Mapping[str, Any]], key: str) -> float:
    return round(math.fsum(float(item.get(key, 0.0)) for item in items) / max(1, len(items)), 6)


def _hash(value: Mapping[str, Any], blank_key: str | None = None) -> str:
    payload = dict(value)
    if blank_key is not None:
        payload["integrity"] = {**_mapping(value.get("integrity")), blank_key: ""}
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def _list_of_mappings(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
