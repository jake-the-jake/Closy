from __future__ import annotations

from copy import deepcopy
from html import escape
from pathlib import Path
from typing import Any, Literal, cast

from closy_forge.contracts.common import COORDINATE_CONVENTION
from closy_forge.geometry.curves import sample_curve
from closy_forge.geometry.mesh_model import MeshSet, Vec3, mesh_bounds, triangle_normal
from closy_forge.package_io.canonical_json import canonical_dumps, write_canonical_json
from closy_forge.package_io.hashing import (
    geometry_content_hash,
    sha256_bytes,
    sha256_file,
    topology_hash,
)

INSPECTION_RENDERER_VERSION = "closy.inspection_renderer.deterministic_svg.v1"
INSPECTION_ARTIFACT_REPORT_VERSION = "closy.inspection_artifact_report.bp47.v1"

WIDTH = 640
HEIGHT = 480
MARGIN = 48.0
SVG_COLOR_SPACE = "srgb"
COORDINATE_VIEW_DESCRIPTION = (
    "right-handed Y-up metres; front projects X/Y, side projects Z/Y, "
    "three-quarter projects (X+Z)/sqrt(2)/Y"
)

ViewId = Literal["front", "side", "three_quarter", "top"]

_PANEL_PALETTE = [
    "#1d4ed8",
    "#047857",
    "#b45309",
    "#be185d",
    "#6d28d9",
    "#0891b2",
    "#65a30d",
]

_REQUIRED_ARTIFACTS: tuple[dict[str, Any], ...] = (
    {
        "artifactId": "pattern_panels_labels",
        "path": "reports/inspection/pattern_panels_labels.svg",
        "viewId": "pattern_2d",
        "overlayKind": "panel_seam_opening_labels",
        "evidenceTier": "topology_representation_inspection",
        "purpose": "pattern panels with stable panel, seam and opening labels",
    },
    {
        "artifactId": "rest_simulation_mesh_front",
        "path": "reports/inspection/rest_simulation_mesh_front.svg",
        "viewId": "front",
        "overlayKind": "wireframe_panel_overlay",
        "evidenceTier": "topology_representation_inspection",
        "purpose": "rest simulation mesh front inspection",
    },
    {
        "artifactId": "rest_simulation_mesh_side_depth",
        "path": "reports/inspection/rest_simulation_mesh_side_depth.svg",
        "viewId": "side",
        "overlayKind": "wireframe_depth_diagnostic",
        "evidenceTier": "topology_representation_inspection",
        "purpose": "rest simulation mesh side/depth inspection",
    },
    {
        "artifactId": "settled_garment_on_avatar_front",
        "path": "reports/inspection/settled_garment_on_avatar_front.svg",
        "viewId": "front",
        "overlayKind": "avatar_collision_overlay",
        "evidenceTier": "topology_representation_inspection",
        "purpose": "settled garment on fixed avatar/collision proxy",
    },
    {
        "artifactId": "canonical_render_shell_front",
        "path": "reports/inspection/canonical_render_shell_front.svg",
        "viewId": "front",
        "overlayKind": "render_shell_wireframe",
        "evidenceTier": "canonical_simulation_to_render_silhouette_preservation",
        "purpose": "canonical render shell representation",
    },
    {
        "artifactId": "manual_raw_proposal_front",
        "path": "reports/inspection/manual_raw_proposal_front.svg",
        "viewId": "front",
        "overlayKind": "raw_proposal_panel_overlay",
        "evidenceTier": "topology_representation_inspection",
        "purpose": "manual/raw proposal preview",
    },
    {
        "artifactId": "cleanup_preview_front",
        "path": "reports/inspection/cleanup_preview_front.svg",
        "viewId": "front",
        "overlayKind": "cleanup_preview_overlay",
        "evidenceTier": "topology_representation_inspection",
        "purpose": "cleanup preview",
    },
    {
        "artifactId": "repair_preview_front",
        "path": "reports/inspection/repair_preview_front.svg",
        "viewId": "front",
        "overlayKind": "repair_preview_overlay",
        "evidenceTier": "topology_representation_inspection",
        "purpose": "repair preview",
    },
    {
        "artifactId": "runtime_bound_preview_front",
        "path": "reports/inspection/runtime_bound_preview_front.svg",
        "viewId": "front",
        "overlayKind": "runtime_bound_wireframe",
        "evidenceTier": "canonical_simulation_to_render_silhouette_preservation",
        "purpose": "runtime-bound preview",
    },
    {
        "artifactId": "logical_stitched_candidate_front",
        "path": "reports/inspection/logical_stitched_candidate_front.svg",
        "viewId": "front",
        "overlayKind": "logical_stitched_candidate_overlay",
        "evidenceTier": "topology_representation_inspection",
        "purpose": "BP46 logical stitched analysis shell",
    },
    {
        "artifactId": "render_split_stitched_candidate_front",
        "path": "reports/inspection/render_split_stitched_candidate_front.svg",
        "viewId": "front",
        "overlayKind": "render_split_stitched_candidate_overlay",
        "evidenceTier": "topology_representation_inspection",
        "purpose": "BP46 render-split/conventional stitched shell",
    },
    {
        "artifactId": "topology_problem_overlay_front",
        "path": "reports/inspection/topology_problem_overlay_front.svg",
        "viewId": "front",
        "overlayKind": "non_manifold_duplicate_boundary_seam_binding_gap_overlay",
        "evidenceTier": "topology_representation_inspection",
        "purpose": "topology problem overlay",
    },
)


def write_inspection_artifacts(
    package_dir: Path,
    *,
    garment_id: str,
    garment_class: str,
    pattern: dict[str, Any],
    rest_mesh: MeshSet,
    settled_mesh: MeshSet,
    render_mesh: MeshSet,
    avatar_collision_mesh: MeshSet,
    manual_raw_mesh: MeshSet,
    cleanup_preview_mesh: MeshSet,
    repair_preview_mesh: MeshSet,
    runtime_bound_mesh: MeshSet,
    logical_stitched_mesh: MeshSet,
    render_split_stitched_mesh: MeshSet,
    geometry_stitched_shell: dict[str, Any],
    geometry_visual_shell_review: dict[str, Any],
    clean_geometry_proposal: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Write deterministic BP47 review artifacts into a Forge package.

    This is intentionally a text/SVG inspection path, not product rendering and
    not source/provider visual fidelity. It gives CI and humans stable topology
    evidence while keeping BP46's stitched-shell candidate rejected.
    """

    artifacts = [
        _write_artifact(
            package_dir,
            spec=_REQUIRED_ARTIFACTS[0],
            svg=_pattern_svg(pattern),
            semantic_ids=_semantic_ids(pattern),
            source_hashes=_source_hashes(package_dir, ["pattern/pattern.json"]),
            metrics={"panelCount": len(pattern["panels"])},
        ),
        _mesh_artifact(
            package_dir,
            spec=_REQUIRED_ARTIFACTS[1],
            meshset=rest_mesh,
            semantic_ids=_mesh_semantic_ids(rest_mesh),
            source_hashes=_source_hashes(
                package_dir,
                ["simulation/mesh_manifest.json", "simulation/rest_state.json"],
            ),
        ),
        _mesh_artifact(
            package_dir,
            spec=_REQUIRED_ARTIFACTS[2],
            meshset=rest_mesh,
            semantic_ids=_mesh_semantic_ids(rest_mesh),
            source_hashes=_source_hashes(
                package_dir,
                ["simulation/mesh_manifest.json", "simulation/rest_state.json"],
            ),
        ),
        _mesh_artifact(
            package_dir,
            spec=_REQUIRED_ARTIFACTS[3],
            meshset=settled_mesh,
            secondary_meshset=avatar_collision_mesh,
            semantic_ids=_mesh_semantic_ids(settled_mesh),
            source_hashes=_source_hashes(
                package_dir,
                [
                    "simulation/mesh_manifest.json",
                    "simulation/settled_state.json",
                    "avatar/collision.glb",
                ],
            ),
        ),
        _mesh_artifact(
            package_dir,
            spec=_REQUIRED_ARTIFACTS[4],
            meshset=render_mesh,
            semantic_ids=_mesh_semantic_ids(render_mesh),
            source_hashes=_source_hashes(
                package_dir,
                ["render/fallback.glb", "render/mesh_manifest.json"],
            ),
        ),
        _mesh_artifact(
            package_dir,
            spec=_REQUIRED_ARTIFACTS[5],
            meshset=manual_raw_mesh,
            semantic_ids=_mesh_semantic_ids(manual_raw_mesh),
            source_hashes=_source_hashes(
                package_dir,
                [
                    "proposals/manual_raw_visual_proposal.glb",
                    "proposals/raw_geometry_proposal.json",
                ],
            ),
        ),
        _mesh_artifact(
            package_dir,
            spec=_REQUIRED_ARTIFACTS[6],
            meshset=cleanup_preview_mesh,
            semantic_ids=_mesh_semantic_ids(cleanup_preview_mesh),
            source_hashes=_source_hashes(
                package_dir,
                ["proposals/manual_cleanup_preview.glb", "reports/geometry_cleanup_result.json"],
            ),
        ),
        _mesh_artifact(
            package_dir,
            spec=_REQUIRED_ARTIFACTS[7],
            meshset=repair_preview_mesh,
            semantic_ids=_mesh_semantic_ids(repair_preview_mesh),
            source_hashes=_source_hashes(
                package_dir,
                ["proposals/manual_repair_preview.glb", "reports/geometry_repair_result.json"],
            ),
        ),
        _mesh_artifact(
            package_dir,
            spec=_REQUIRED_ARTIFACTS[8],
            meshset=runtime_bound_mesh,
            semantic_ids=_mesh_semantic_ids(runtime_bound_mesh),
            source_hashes=_source_hashes(
                package_dir,
                [
                    "proposals/manual_runtime_retopology_preview.glb",
                    "reports/geometry_runtime_binding_result.json",
                    "binding/proposal_binding_manifest.json",
                ],
            ),
        ),
        _mesh_artifact(
            package_dir,
            spec=_REQUIRED_ARTIFACTS[9],
            meshset=logical_stitched_mesh,
            semantic_ids=_mesh_semantic_ids(logical_stitched_mesh),
            source_hashes=_source_hashes(
                package_dir,
                [
                    "stitch/logical_stitched_analysis_shell.json",
                    "reports/geometry_stitched_shell.json",
                ],
            ),
        ),
        _mesh_artifact(
            package_dir,
            spec=_REQUIRED_ARTIFACTS[10],
            meshset=render_split_stitched_mesh,
            semantic_ids=_mesh_semantic_ids(render_split_stitched_mesh),
            source_hashes=_source_hashes(
                package_dir,
                ["render/stitched_shell.glb", "reports/geometry_stitched_shell.json"],
            ),
        ),
        _mesh_artifact(
            package_dir,
            spec=_REQUIRED_ARTIFACTS[11],
            meshset=logical_stitched_mesh,
            semantic_ids=_mesh_semantic_ids(logical_stitched_mesh),
            source_hashes=_source_hashes(
                package_dir,
                [
                    "stitch/logical_stitched_analysis_shell.json",
                    "reports/geometry_stitched_shell.json",
                ],
            ),
            topology_overlay=geometry_stitched_shell.get("topologyAudit", {}),
        ),
    ]

    evidence_tiers = _evidence_tiers(geometry_visual_shell_review)
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "manifestId": "inspection_manifest.demo_tshirt_bp47_v1",
        "stageVersion": INSPECTION_ARTIFACT_REPORT_VERSION,
        "rendererVersion": INSPECTION_RENDERER_VERSION,
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "coordinateConvention": COORDINATE_CONVENTION,
        "rendererSettings": _renderer_settings(),
        "artifactCount": len(artifacts),
        "artifacts": artifacts,
        "requiredArtifactIds": [str(spec["artifactId"]) for spec in _REQUIRED_ARTIFACTS],
        "evidenceTiers": evidence_tiers,
        "policy": _policy(),
        "limitations": _limitations(clean_geometry_proposal),
        "integrity": {"inspectionManifestHash": ""},
    }
    manifest["integrity"]["inspectionManifestHash"] = hash_inspection_artifact_manifest(manifest)
    write_canonical_json(package_dir / "reports" / "inspection" / "manifest.json", manifest)

    report: dict[str, Any] = {
        "schemaVersion": 1,
        "reportId": "inspection_report.demo_tshirt_bp47_v1",
        "stageVersion": INSPECTION_ARTIFACT_REPORT_VERSION,
        "garmentId": garment_id,
        "garmentClass": garment_class,
        "manifestPath": "reports/inspection/manifest.json",
        "manifestHash": manifest["integrity"]["inspectionManifestHash"],
        "renderer": _renderer_settings(),
        "sourceHashes": _source_hashes(
            package_dir,
            [
                "pattern/pattern.json",
                "simulation/mesh_manifest.json",
                "simulation/rest_state.json",
                "simulation/settled_state.json",
                "render/mesh_manifest.json",
                "reports/geometry_stitched_shell.json",
                "reports/geometry_visual_shell_review.json",
                "reports/geometry_clean_acceptance_gate.json",
                "proposals/clean_geometry_proposal.json",
            ],
        ),
        "metrics": {
            "artifactCount": len(artifacts),
            "representationInspectionArtifactCount": sum(
                1
                for artifact in artifacts
                if artifact["evidenceTier"] == "topology_representation_inspection"
            ),
            "canonicalSimulationToRenderArtifactCount": sum(
                1
                for artifact in artifacts
                if artifact["evidenceTier"]
                == "canonical_simulation_to_render_silhouette_preservation"
            ),
            "stitchedNonManifoldEdgeCount": geometry_stitched_shell["topologyAudit"][
                "nonManifoldEdgeCount"
            ],
            "stitchedDuplicateFaceCount": geometry_stitched_shell["topologyAudit"][
                "duplicateFaceCount"
            ],
            "stitchedBoundaryLoopCount": geometry_stitched_shell["topologyAudit"][
                "boundaryLoopCount"
            ],
            "representationSilhouetteAccepted": geometry_visual_shell_review["readiness"][
                "representationSilhouetteAccepted"
            ],
        },
        "evidenceTiers": evidence_tiers,
        "readiness": {
            "topologyRepresentationInspectionRun": True,
            "canonicalSimulationToRenderSilhouetteRun": True,
            "providerGeometryAppearanceComparisonRun": False,
            "sourceImageSilhouetteComparisonRun": False,
            "sourceImageAppearanceComparisonRun": False,
            "humanVisualReviewRun": False,
            "acceptedForVisualFidelity": False,
            "acceptedForCleanProposal": False,
        },
        "policy": _policy(),
        "limitations": _limitations(clean_geometry_proposal),
        "integrity": {"inspectionReportHash": ""},
    }
    report["integrity"]["inspectionReportHash"] = hash_inspection_artifact_report(report)
    write_canonical_json(package_dir / "reports" / "inspection" / "inspection_report.json", report)
    return manifest, report


def hash_inspection_artifact_manifest(manifest: dict[str, Any]) -> str:
    payload = deepcopy(manifest)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["inspectionManifestHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def hash_inspection_artifact_report(report: dict[str, Any]) -> str:
    payload = deepcopy(report)
    integrity = payload.get("integrity")
    if isinstance(integrity, dict):
        integrity["inspectionReportHash"] = ""
    return sha256_bytes(canonical_dumps(payload).encode("utf-8"))


def project_mesh_signature(
    meshset: MeshSet,
    view_id: ViewId,
    *,
    include_depth: bool = False,
) -> str:
    projected: list[dict[str, Any]] = []
    for mesh in meshset.meshes:
        for tri_index, tri in enumerate(mesh.triangles):
            points = [_project(mesh.vertices[index], view_id) for index in tri]
            item: dict[str, Any] = {
                "mesh": mesh.name,
                "panel": mesh.panel_id,
                "triangle": tri_index,
                "xy": [[_round(x), _round(y)] for x, y, _depth in points],
            }
            if include_depth:
                item["depth"] = [_round(depth) for _x, _y, depth in points]
            projected.append(item)
    return sha256_bytes(canonical_dumps(projected).encode("utf-8"))


def required_artifact_specs() -> tuple[dict[str, Any], ...]:
    return _REQUIRED_ARTIFACTS


def _write_artifact(
    package_dir: Path,
    *,
    spec: dict[str, Any],
    svg: str,
    semantic_ids: list[str],
    source_hashes: dict[str, str],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    rel_path = str(spec["path"])
    path = package_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg.rstrip("\n") + "\n", encoding="utf-8", newline="\n")
    return _artifact_record(
        spec,
        source_hashes=source_hashes,
        semantic_ids=semantic_ids,
        metrics=metrics,
        content_hash=sha256_file(path),
        byte_size=path.stat().st_size,
    )


def _mesh_artifact(
    package_dir: Path,
    *,
    spec: dict[str, Any],
    meshset: MeshSet,
    semantic_ids: list[str],
    source_hashes: dict[str, str],
    secondary_meshset: MeshSet | None = None,
    topology_overlay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    view_id = str(spec["viewId"])
    if view_id not in {"front", "side", "three_quarter", "top"}:
        raise ValueError(f"unsupported mesh inspection view: {view_id}")
    mesh_view_id = cast(ViewId, view_id)
    svg = _mesh_svg(
        meshset,
        mesh_view_id,
        title=str(spec["purpose"]),
        secondary_meshset=secondary_meshset,
        topology_overlay=topology_overlay,
    )
    return _write_artifact(
        package_dir,
        spec=spec,
        svg=svg,
        semantic_ids=semantic_ids,
        source_hashes=source_hashes,
        metrics={
            "meshCount": len(meshset.meshes),
            "vertexCount": meshset.vertex_count,
            "triangleCount": meshset.triangle_count,
            "topologyHash": topology_hash(meshset),
            "contentHash": geometry_content_hash(meshset),
            "projectionSignature": project_mesh_signature(
                meshset, mesh_view_id, include_depth=mesh_view_id != "front"
            ),
        },
    )


def _artifact_record(
    spec: dict[str, Any],
    *,
    source_hashes: dict[str, str],
    semantic_ids: list[str],
    metrics: dict[str, Any],
    content_hash: str,
    byte_size: int,
) -> dict[str, Any]:
    view_id = str(spec["viewId"])
    return {
        "artifactId": str(spec["artifactId"]),
        "path": str(spec["path"]),
        "sourceAssetHashes": source_hashes,
        "rendererVersion": INSPECTION_RENDERER_VERSION,
        "camera": _camera_for_view(view_id),
        "width": WIDTH,
        "height": HEIGHT,
        "format": "svg",
        "colorSpace": SVG_COLOR_SPACE,
        "overlayKind": str(spec["overlayKind"]),
        "semanticIdsIncluded": semantic_ids,
        "contentHash": content_hash,
        "byteSize": byte_size,
        "syntheticPublicSafe": True,
        "comparisonTarget": None,
        "metrics": metrics,
        "thresholds": _thresholds_for_tier(str(spec["evidenceTier"])),
        "evidenceTier": str(spec["evidenceTier"]),
        "purpose": str(spec["purpose"]),
        "limitations": [
            "deterministic_svg_inspection_not_photometric_render",
            "not_source_or_provider_visual_fidelity",
            "human_review_not_signed",
        ],
    }


def _mesh_svg(
    meshset: MeshSet,
    view_id: ViewId,
    *,
    title: str,
    secondary_meshset: MeshSet | None = None,
    topology_overlay: dict[str, Any] | None = None,
) -> str:
    bounds = _combined_bounds(meshset, secondary_meshset)
    projected_bounds = _projected_bounds(bounds, view_id)

    def point(vertex: Vec3) -> tuple[float, float, float]:
        return _screen_point(_project(vertex, view_id), projected_bounds)

    parts: list[str] = [
        _svg_header(title),
        '<rect x="0" y="0" width="640" height="480" fill="#f8fafc"/>',
        (
            '<text x="18" y="28" font-family="monospace" font-size="13" '
            f'fill="#0f172a">{escape(title)}</text>'
        ),
        (
            '<text x="18" y="46" font-family="monospace" font-size="10" '
            f'fill="#475569">view={view_id} renderer={INSPECTION_RENDERER_VERSION}</text>'
        ),
    ]
    if secondary_meshset is not None:
        parts.extend(_mesh_polygons(secondary_meshset, point, opacity=0.15, stroke="#94a3b8"))
    parts.extend(_mesh_polygons(meshset, point, opacity=0.56, stroke="#0f172a"))
    parts.extend(_mesh_wireframe(meshset, point, stroke="#0f172a", stroke_width=0.55))
    parts.extend(_mesh_labels(meshset, point))
    if topology_overlay:
        parts.extend(_topology_overlay(meshset, point, topology_overlay))
    parts.append("</svg>")
    return "\n".join(parts)


def _pattern_svg(pattern: dict[str, Any]) -> str:
    parts: list[str] = [
        _svg_header("pattern panels labels"),
        '<rect x="0" y="0" width="640" height="480" fill="#fffaf0"/>',
        (
            '<text x="18" y="28" font-family="monospace" font-size="13" '
            'fill="#0f172a">pattern panels, seams and semantic openings</text>'
        ),
    ]
    all_samples: list[tuple[float, float]] = []
    panel_samples: list[tuple[dict[str, Any], list[tuple[float, float]]]] = []
    for panel in pattern["panels"]:
        samples: list[tuple[float, float]] = []
        for edge in panel["boundary"]:
            edge_samples = sample_curve(edge["curve"], int(edge["sampleCount"]))
            if samples and edge_samples and samples[-1] == edge_samples[0]:
                edge_samples = edge_samples[1:]
            samples.extend(edge_samples)
        if samples:
            all_samples.extend(samples)
            panel_samples.append((panel, samples))
    scale, tx, ty = _fit_2d_transform(all_samples)
    for panel_index, (panel, samples) in enumerate(panel_samples):
        points = " ".join(
            f"{x * scale + tx:.3f},{HEIGHT - (y * scale + ty):.3f}" for x, y in samples
        )
        color = _PANEL_PALETTE[panel_index % len(_PANEL_PALETTE)]
        parts.append(
            f'<polygon points="{points}" fill="{color}" fill-opacity="0.12" '
            f'stroke="{color}" stroke-width="1.6"/>'
        )
        cx = sum(x for x, _y in samples) / len(samples)
        cy = sum(y for _x, y in samples) / len(samples)
        parts.append(
            f'<text x="{cx * scale + tx:.3f}" y="{HEIGHT - (cy * scale + ty):.3f}" '
            'font-family="monospace" font-size="10" text-anchor="middle" '
            f'fill="#0f172a">{escape(str(panel["id"]))}</text>'
        )
    y = 64
    for label, items in [
        ("seams", [seam["id"] for seam in pattern["seams"]]),
        ("openings", [opening["id"] for opening in pattern["openings"]]),
    ]:
        parts.append(
            f'<text x="18" y="{y}" font-family="monospace" font-size="10" '
            f'fill="#334155">{label}: {escape(", ".join(items))}</text>'
        )
        y += 16
    parts.append("</svg>")
    return "\n".join(parts)


def _svg_header(title: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="{escape(title)}">'
    )


def _mesh_polygons(
    meshset: MeshSet,
    point_fn: Any,
    *,
    opacity: float,
    stroke: str,
) -> list[str]:
    parts: list[str] = []
    for mesh_index, mesh in enumerate(meshset.meshes):
        color = _PANEL_PALETTE[mesh_index % len(_PANEL_PALETTE)]
        tri_order = sorted(
            enumerate(mesh.triangles),
            key=lambda item: (
                _triangle_depth(mesh.vertices, item[1]),
                mesh.panel_id,
                item[0],
            ),
        )
        for tri_index, tri in tri_order:
            normal = triangle_normal(mesh.vertices, tri)
            shade = 0.72 + 0.18 * max(0.0, normal[1])
            points = " ".join(
                f"{point_fn(mesh.vertices[index])[0]:.3f},{point_fn(mesh.vertices[index])[1]:.3f}"
                for index in tri
            )
            parts.append(
                f'<polygon data-panel="{escape(mesh.panel_id)}" data-triangle="{tri_index}" '
                f'points="{points}" fill="{color}" fill-opacity="{opacity * shade:.3f}" '
                f'stroke="{stroke}" stroke-opacity="0.18" stroke-width="0.25"/>'
            )
    return parts


def _mesh_wireframe(
    meshset: MeshSet,
    point_fn: Any,
    *,
    stroke: str,
    stroke_width: float,
) -> list[str]:
    parts: list[str] = []
    for mesh in meshset.meshes:
        for tri in mesh.triangles:
            coords = [point_fn(mesh.vertices[index]) for index in tri]
            path = (
                f"M {coords[0][0]:.3f} {coords[0][1]:.3f} "
                f"L {coords[1][0]:.3f} {coords[1][1]:.3f} "
                f"L {coords[2][0]:.3f} {coords[2][1]:.3f} Z"
            )
            parts.append(
                f'<path d="{path}" fill="none" stroke="{stroke}" '
                f'stroke-width="{stroke_width:.3f}" stroke-opacity="0.46"/>'
            )
    return parts


def _mesh_labels(meshset: MeshSet, point_fn: Any) -> list[str]:
    parts: list[str] = []
    for mesh in meshset.meshes:
        if not mesh.vertices:
            continue
        cx = sum(v[0] for v in mesh.vertices) / len(mesh.vertices)
        cy = sum(v[1] for v in mesh.vertices) / len(mesh.vertices)
        cz = sum(v[2] for v in mesh.vertices) / len(mesh.vertices)
        x, y, _depth = point_fn((cx, cy, cz))
        parts.append(
            f'<text x="{x:.3f}" y="{y:.3f}" font-family="monospace" font-size="9" '
            f'text-anchor="middle" fill="#111827">{escape(mesh.panel_id)}</text>'
        )
    return parts


def _topology_overlay(
    meshset: MeshSet,
    point_fn: Any,
    topology: dict[str, Any],
) -> list[str]:
    parts = [
        '<g data-overlay="topology-problems">',
        (
            '<text x="18" y="438" font-family="monospace" font-size="10" '
            f'fill="#991b1b">nonManifoldEdges={topology.get("nonManifoldEdgeCount")} '
            f'duplicateFaces={topology.get("duplicateFaceCount")} '
            f'boundaryLoops={topology.get("boundaryLoopCount")} '
            f'bindingCoverage={topology.get("bindingCoverage")}</text>'
        ),
    ]
    edge_counts: dict[tuple[int, int], int] = {}
    offset = 0
    for mesh in meshset.meshes:
        for tri in mesh.triangles:
            for a, b in [(tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])]:
                left = min(a + offset, b + offset)
                right = max(a + offset, b + offset)
                key = (left, right)
                edge_counts[key] = edge_counts.get(key, 0) + 1
        offset += len(mesh.vertices)
    flat_vertices = [vertex for mesh in meshset.meshes for vertex in mesh.vertices]
    for (a, b), count in sorted(edge_counts.items()):
        if count == 2:
            continue
        va = point_fn(flat_vertices[a])
        vb = point_fn(flat_vertices[b])
        color = "#f97316" if count == 1 else "#dc2626"
        width = 1.15 if count == 1 else 2.0
        parts.append(
            f'<line x1="{va[0]:.3f}" y1="{va[1]:.3f}" x2="{vb[0]:.3f}" y2="{vb[1]:.3f}" '
            f'stroke="{color}" stroke-width="{width:.2f}" stroke-opacity="0.84"/>'
        )
    parts.append("</g>")
    return parts


def _project(vertex: Vec3, view_id: ViewId) -> tuple[float, float, float]:
    x, y, z = vertex
    if view_id == "front":
        return x, y, z
    if view_id == "side":
        return z, y, x
    if view_id == "top":
        return x, z, y
    return (x + z) * 0.7071067811865475, y, (z - x) * 0.7071067811865475


def _screen_point(
    projected: tuple[float, float, float],
    projected_bounds: tuple[float, float, float, float],
) -> tuple[float, float, float]:
    x, y, depth = projected
    min_x, min_y, max_x, max_y = projected_bounds
    span_x = max(max_x - min_x, 1e-6)
    span_y = max(max_y - min_y, 1e-6)
    scale = min((WIDTH - 2 * MARGIN) / span_x, (HEIGHT - 2 * MARGIN) / span_y)
    sx = (x - min_x) * scale + (WIDTH - span_x * scale) / 2
    sy = HEIGHT - ((y - min_y) * scale + (HEIGHT - span_y * scale) / 2)
    return sx, sy, depth


def _projected_bounds(
    bounds: dict[str, list[float]],
    view_id: ViewId,
) -> tuple[float, float, float, float]:
    mins = bounds["min"]
    maxs = bounds["max"]
    corners = [
        (x, y, z)
        for x in [mins[0], maxs[0]]
        for y in [mins[1], maxs[1]]
        for z in [mins[2], maxs[2]]
    ]
    projected = [_project(corner, view_id) for corner in corners]
    xs = [point[0] for point in projected]
    ys = [point[1] for point in projected]
    return min(xs), min(ys), max(xs), max(ys)


def _combined_bounds(primary: MeshSet, secondary: MeshSet | None) -> dict[str, list[float]]:
    if secondary is None:
        return mesh_bounds(primary)
    primary_bounds = mesh_bounds(primary)
    secondary_bounds = mesh_bounds(secondary)
    return {
        "min": [
            min(primary_bounds["min"][index], secondary_bounds["min"][index]) for index in range(3)
        ],
        "max": [
            max(primary_bounds["max"][index], secondary_bounds["max"][index]) for index in range(3)
        ],
        "size": [
            max(primary_bounds["max"][index], secondary_bounds["max"][index])
            - min(primary_bounds["min"][index], secondary_bounds["min"][index])
            for index in range(3)
        ],
    }


def _fit_2d_transform(points: list[tuple[float, float]]) -> tuple[float, float, float]:
    if not points:
        return 1.0, MARGIN, MARGIN
    min_x = min(x for x, _y in points)
    max_x = max(x for x, _y in points)
    min_y = min(y for _x, y in points)
    max_y = max(y for _x, y in points)
    span_x = max(max_x - min_x, 1e-6)
    span_y = max(max_y - min_y, 1e-6)
    scale = min((WIDTH - 2 * MARGIN) / span_x, (HEIGHT - 2 * MARGIN) / span_y)
    tx = (WIDTH - span_x * scale) / 2 - min_x * scale
    ty = (HEIGHT - span_y * scale) / 2 - min_y * scale
    return scale, tx, ty


def _camera_for_view(view_id: str) -> dict[str, Any]:
    if view_id in {"pattern_2d", "front"}:
        direction = [0.0, 0.0, 1.0]
    elif view_id == "side":
        direction = [1.0, 0.0, 0.0]
    elif view_id == "top":
        direction = [0.0, 1.0, 0.0]
    else:
        direction = [0.7071067812, 0.0, 0.7071067812]
    return {
        "viewId": view_id,
        "projection": "orthographic",
        "direction": direction,
        "near": -10.0,
        "far": 10.0,
        "coordinateConvention": COORDINATE_VIEW_DESCRIPTION,
    }


def _renderer_settings() -> dict[str, Any]:
    return {
        "rendererId": "closy.bp47.deterministic_svg_inspection",
        "rendererVersion": INSPECTION_RENDERER_VERSION,
        "width": WIDTH,
        "height": HEIGHT,
        "format": "svg",
        "colorSpace": SVG_COLOR_SPACE,
        "projection": "orthographic",
        "near": -10.0,
        "far": 10.0,
        "background": "#f8fafc",
        "lineWidthPixels": 1.0,
        "drawOrder": "mesh_name_panel_id_triangle_depth_triangle_index",
        "edgeRules": "svg_vector_paths_sorted_deterministically",
        "lighting": "synthetic_normal_y_shade_no_photometric_lighting",
        "gamma": "not_applicable_vector_svg",
        "palette": {
            "boundary": "#f97316",
            "nonManifold": "#dc2626",
            "wireframe": "#0f172a",
            "avatarCollision": "#94a3b8",
        },
    }


def _thresholds_for_tier(tier: str) -> dict[str, Any]:
    if tier == "canonical_simulation_to_render_silhouette_preservation":
        return {"representationSilhouetteDifferenceMax": 0.01}
    return {"inspectionArtifactHashMustMatch": True, "sourceHashesMustMatch": True}


def _source_hashes(package_dir: Path, relpaths: list[str]) -> dict[str, str]:
    return {relpath: sha256_file(package_dir / relpath) for relpath in relpaths}


def _semantic_ids(pattern: dict[str, Any]) -> list[str]:
    return sorted(
        [panel["id"] for panel in pattern["panels"]]
        + [seam["id"] for seam in pattern["seams"]]
        + [opening["id"] for opening in pattern["openings"]]
    )


def _mesh_semantic_ids(meshset: MeshSet) -> list[str]:
    return sorted({mesh.panel_id for mesh in meshset.meshes})


def _evidence_tiers(geometry_visual_shell_review: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "tier": "topology_representation_inspection",
            "status": "run",
            "accepted": False,
            "artifactIds": [
                str(spec["artifactId"])
                for spec in _REQUIRED_ARTIFACTS
                if spec["evidenceTier"] == "topology_representation_inspection"
            ],
            "limitations": ["representation inspection only; not appearance fidelity"],
        },
        {
            "tier": "canonical_simulation_to_render_silhouette_preservation",
            "status": "run",
            "accepted": bool(
                geometry_visual_shell_review["readiness"]["representationSilhouetteAccepted"]
            ),
            "artifactIds": [
                str(spec["artifactId"])
                for spec in _REQUIRED_ARTIFACTS
                if spec["evidenceTier"] == "canonical_simulation_to_render_silhouette_preservation"
            ],
            "limitations": [
                "representation silhouette only; side/depth artifacts retained separately"
            ],
        },
        {
            "tier": "independent_provider_geometry_appearance_comparison",
            "status": "not_run",
            "accepted": False,
            "artifactIds": [],
            "limitations": [
                "no independent provider target is available in this synthetic package"
            ],
        },
        {
            "tier": "source_image_silhouette_comparison",
            "status": "not_run",
            "accepted": False,
            "artifactIds": [],
            "limitations": ["no source raster image evidence exists before BP49/BP50"],
        },
        {
            "tier": "source_image_appearance_texture_logo_comparison",
            "status": "not_run",
            "accepted": False,
            "artifactIds": [],
            "limitations": ["no source texture projection or logo evidence exists"],
        },
        {
            "tier": "human_visual_review",
            "status": "not_run",
            "accepted": False,
            "artifactIds": [],
            "limitations": ["no signed human review record exists"],
        },
    ]


def _policy() -> dict[str, Any]:
    return {
        "syntheticPublicSafe": True,
        "allowExternalApis": False,
        "allowTrainingUse": False,
        "containsUserImagery": False,
        "containsPersonalBodyData": False,
        "checkedInGoldenAllowed": True,
    }


def _limitations(clean_geometry_proposal: dict[str, Any]) -> list[str]:
    limitations = [
        "svg_inspection_artifacts_are_not_product_renders",
        "topology_representation_evidence_separate_from_visual_fidelity",
        "source_provider_human_visual_fidelity_not_run",
    ]
    if clean_geometry_proposal["cleanProposal"]["available"] is not True:
        limitations.append("clean_candidate_artifact_omitted_because_no_clean_candidate_exists")
    return limitations


def _triangle_depth(vertices: list[Vec3], tri: tuple[int, int, int]) -> float:
    return sum(vertices[index][2] for index in tri) / 3.0


def _round(value: float) -> float:
    return round(float(value), 9)
