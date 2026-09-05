"""Build/reuse verified garments, solve a real outfit, and rasterize actual geometry."""

from __future__ import annotations

import argparse
import math
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from publish_family_integration_v1 import source_closure

from closy_forge.binding.binary_format import read_binding
from closy_forge.binding.reconstruct import reconstruct_vertices
from closy_forge.family_integration_v1.compiler import compile_family, validate_family
from closy_forge.family_integration_v1.registry import FAMILIES
from closy_forge.geometry.glb_io import read_glb_meshset, write_indexed_glb
from closy_forge.geometry.mesh_model import MeshSet, Vec3, mesh_bounds
from closy_forge.inspection.cpu_raster import rasterize_settled_garment
from closy_forge.manual_provider_binding_v2.binding import (
    build_binding_v2,
    read_binding_v2,
    reconstruct_v2,
)
from closy_forge.manual_provider_binding_v2.checker import check_rest
from closy_forge.manual_provider_c3_v1.states import MOTION_STATES
from closy_forge.package_io.canonical_json import read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_file
from closy_forge.package_layering_v1.contracts import LayerSpec, load_layers
from closy_forge.package_layering_v1.solver import solve
from closy_forge.simulation.reference_cloth_solver import flatten_mesh, replace_mesh_positions

CELL_W, CELL_H = 320, 320
FONT = ImageFont.load_default(size=15)


def panel_image(mesh: MeshSet, azimuth: float, label: str) -> Image.Image:
    bounds = mesh_bounds(mesh)
    center = [(a + b) / 2 for a, b in zip(bounds["min"], bounds["max"], strict=True)]
    factor = min(
        0.68 / max(bounds["size"][1], 1e-4),
        1.55 / max(math.hypot(bounds["size"][0], bounds["size"][2]), 1e-4),
    )
    display = MeshSet(
        [
            replace(
                m,
                vertices=[
                    (
                        (p[0] - center[0]) * factor,
                        (p[1] - center[1]) * factor + 1.04,
                        (p[2] - center[2]) * factor,
                    )
                    for p in m.vertices
                ],
            )
            for m in mesh.meshes
        ]
    )
    colours = ((63, 108, 122, 255), (129, 89, 67, 255), (108, 124, 82, 255), (89, 87, 126, 255))
    panels = sorted(m.panel_id for m in mesh.meshes)
    rendered = rasterize_settled_garment(
        display,
        label="front",
        width=CELL_W,
        height=CELL_H - 32,
        camera={"projection": "orthographic", "azimuthDegrees": azimuth, "elevationDegrees": 9},
        visible_panel_ids=set(panels),
        background=(245, 243, 238, 255),
        texture_sampler=lambda panel, uv: colours[panels.index(panel) % len(colours)],
    )
    if not rendered.foreground:
        raise ValueError(f"empty_inspection_raster:{label}")
    image = Image.new("RGB", (CELL_W, CELL_H), (245, 243, 238))
    image.paste(
        Image.frombytes("RGBA", (rendered.width, rendered.height), rendered.rgba).convert("RGB"),
        (0, 32),
    )
    ImageDraw.Draw(image).text((10, 9), label, fill=(32, 40, 43), font=FONT)
    return image


def wire_panel(triangles: list[list[Vec3]], label: str, colour: str) -> Image.Image:
    image = Image.new("RGB", (480, 320), (246, 244, 239))
    draw = ImageDraw.Draw(image)
    projected = [[(p[0] + 0.4 * p[2], p[1]) for p in tri] for tri in triangles]
    points = [p for tri in projected for p in tri]
    min_x, max_x = min(p[0] for p in points), max(p[0] for p in points)
    min_y, max_y = min(p[1] for p in points), max(p[1] for p in points)
    factor = min(420 / max(max_x - min_x, 1e-4), 225 / max(max_y - min_y, 1e-4))
    for triangle in projected:
        pixels = [
            (
                240 + (p[0] - (max_x + min_x) / 2) * factor,
                185 - (p[1] - (max_y + min_y) / 2) * factor,
            )
            for p in triangle
        ]
        draw.line([*pixels, pixels[0]], fill=colour, width=3)
        for x, y in pixels:
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=colour)
    draw.text((10, 10), label, fill=(32, 40, 43), font=FONT)
    draw.text(
        (10, 38),
        "Actual triangle positions; independent local framing",
        fill=(90, 90, 90),
        font=FONT,
    )
    return image


def repair_images(forge: Path, families: Path, output: Path) -> dict[str, Any]:
    original = read_json(
        forge / "docs/evidence/phase10_zeroone_static/z1_surface_repair/pre_fix_witnesses.json"
    )
    witness = next(
        w
        for w in original["rejectedFamilyWitnesses"]
        if w["failingTriangles"][0]["panelId"].startswith("panel.long_sleeved_top")
    )
    failures = witness["failingTriangles"]
    before = [[tuple(p) for p in tri["positions"]] for tri in failures]
    repaired = read_glb_meshset(families / "long_sleeved_top/render/fallback.glb")
    after = [
        [
            repaired.meshes[t["meshIndex"]].vertices[i]
            for i in repaired.meshes[t["meshIndex"]].triangles[t["localTriangleIndex"]]
        ]
        for t in failures
    ]
    sheet = Image.new("RGB", (960, 320), "white")
    sheet.paste(
        wire_panel(before, "Before: retained collapsed sleeve witnesses", "#b24c44"), (0, 0)
    )
    sheet.paste(wire_panel(after, "After: same panel/triangle identities", "#397f69"), (480, 0))
    sheet.save(output / "sleeve_before_after.png")
    source = forge / "docs/evidence/manual_provider_c3_v1/packages/manual-tshirt-01"
    clean = read_glb_meshset(source / "render/clean.glb")
    old = reconstruct_vertices(
        read_glb_meshset(source / "render/fallback.glb"),
        read_binding(source / "binding/hybrid_binding.bin"),
    )
    target = output / "binding"
    fresh = build_binding_v2(clean, target)
    write_indexed_glb(target / "cage.glb", fresh.cage, "binding_cage", (0.4, 0.5, 0.6, 1))
    shutil.copyfile(source / "render/clean.glb", target / "clean.glb")
    new = reconstruct_v2(
        read_glb_meshset(target / "cage.glb"),
        read_binding_v2(target / "binding/local_frame_v2.bin"),
    )
    audit = check_rest(
        target / "cage.glb", target / "clean.glb", target / "binding/local_frame_v2.bin"
    )
    reference = flatten_mesh(clean)
    old_errors = [math.dist(a, b) for a, b in zip(old, reference.positions, strict=True)]
    new_errors = [math.dist(a, b) for a, b in zip(new, reference.positions, strict=True)]
    pair = Image.new("RGB", (960, 430), (246, 244, 239))
    for index, (points, errors, name) in enumerate(
        ((old, old_errors, "V1 zero residual"), (new, new_errors, "V2 local frame residual"))
    ):
        mesh = replace_mesh_positions(clean, points, reference.mesh_offsets)
        write_indexed_glb(
            target / f"{index}_reconstructed.glb", mesh, "reconstruction", (0.3, 0.6, 0.6, 1)
        )
        image = panel_image(mesh, 25, f"{name}: max {max(errors)*1000:.6f} mm")
        pair.paste(image.resize((480, 400)), (index * 480, 0))
    ImageDraw.Draw(pair).text(
        (12, 404),
        "Same dense shell; serialized cage/binding reconstruction. No physical claim.",
        fill=(50, 60, 60),
        font=FONT,
    )
    pair.save(output / "binding_before_after.png")
    return {
        "sleeve": {
            "oldFallbackHash": witness["conventionalFallback"]["sha256"],
            "beforeScope": "only_exact_retained_triangle_witnesses_not_full_old_mesh",
            "triangleCount": len(failures),
            "newHash": sha256_file(families / "long_sleeved_top/render/fallback.glb"),
        },
        "binding": {
            "oldMaximumRestM": max(old_errors),
            "newMaximumRestM": max(new_errors),
            "independent": audit,
        },
    }


def run(output: Path, cache: Path | None) -> dict[str, Any]:
    if output.exists():
        raise ValueError("demo_output_must_be_fresh")
    forge = Path(__file__).resolve().parents[1]
    reuse = None
    if cache:
        inventory = read_json(cache.parent / "source_inventory.json")["files"]
        dynamic = [
            f"src/closy_forge/garments/{s.name}/{m}.py"
            for s in FAMILIES
            for m in ("parameters", "pattern_generator", "semantic_graph", "assembly")
        ]
        closure = source_closure(
            forge, ["src/closy_forge/family_integration_v1/compiler.py", *dynamic]
        )
        if any(inventory.get(p) != digest for p, digest in closure.items()):
            raise ValueError("cached_compiler_source_closure_changed")
        reuse = {"compilerClosure": closure, "cache": str(cache), "validated": True}
    output.mkdir(parents=True)
    garments = output / "garments"
    index = []
    for spec in FAMILIES:
        target = garments / spec.name
        if cache:
            validate_family(cache / spec.name / "nominal")
            shutil.copytree(cache / spec.name / "nominal", target)
        else:
            compile_family(spec.name, target)
        index.append(validate_family(target))
        write_canonical_json(output / "checkpoint.json", {"familyAudits": index})
    order = [("top", "trousers", 0.0, 2.5, True)]
    layers = load_layers(
        [
            LayerSpec("top", garments / "tshirt"),
            LayerSpec("trousers", garments / "simple_trousers"),
        ],
        order,
    )
    outfit = solve(layers, order, MOTION_STATES[0], output / "outfit")
    inspection = output / "inspection"
    inspection.mkdir()
    rows = [(s.name, garments / s.name / "render/fallback.glb") for s in FAMILIES]
    rows.append(
        (
            "outfit: " + ("ready" if outfit["ready"] else "collision/fit FAILED"),
            output / "outfit/render.glb",
        )
    )
    sheet = Image.new("RGB", (CELL_W * 3, CELL_H * len(rows)), (246, 244, 239))
    for i, (name, path) in enumerate(rows):
        for j, (azimuth, view) in enumerate(((0.0, "front"), (180.0, "back"), (35.0, "3/4"))):
            sheet.paste(
                panel_image(read_glb_meshset(path), azimuth, f"{name} / {view}"),
                (j * CELL_W, i * CELL_H),
            )
    sheet.save(inspection / "family_contact_sheet.png")
    repair = repair_images(forge, garments, inspection)
    report = {
        "version": "family_outfit_inspection_v1",
        "classification": "synthetic_manual_host_cpu",
        "cacheReuse": reuse,
        "familyAudits": index,
        "outfitReady": outfit["ready"],
        "outfitReport": "outfit/report.json",
        "repairComparison": repair,
        "imageSource": "actual_serialized_geometry_cpu_raster_no_generated_visuals",
        "scientificQualification": False,
        "physicalMobile": "not_run",
    }
    write_canonical_json(output / "report.json", report)
    page = """<!doctype html><html lang="en"><meta charset="utf-8">
<title>Closy garment inspection</title>
<style>body{font:16px Georgia,serif;max-width:1050px;margin:32px auto;
background:#f6f4ef;color:#263536}
img{max-width:100%}h1{font-size:36px}a{color:#296b72}</style><h1>Family and outfit inspection</h1>
<p>Actual synthetic/manual geometry. Valid meshes are not physical drape acceptance.</p>
<p>Read <a href="report.json">audit</a> and
<a href="outfit/report.json">literal outfit outcome</a>.</p>
<img src="inspection/family_contact_sheet.png" alt="All nine families and layered outfit">
<h2>Collapsed sleeve repair</h2><img src="inspection/sleeve_before_after.png"
alt="Recorded collapsed triangles and repaired output">
<h2>Binding repair</h2><img src="inspection/binding_before_after.png"
alt="Serialized rest reconstruction before and after"></html>"""
    (output / "index.html").write_text(page, encoding="utf-8")
    write_canonical_json(
        output / "output_inventory.json",
        [
            {
                "path": p.relative_to(output).as_posix(),
                "sha256": sha256_file(p),
                "bytes": p.stat().st_size,
            }
            for p in sorted(output.rglob("*"))
            if p.is_file()
        ],
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--families-cache", type=Path)
    args = parser.parse_args()
    report = run(
        args.output.resolve(), args.families_cache.resolve() if args.families_cache else None
    )
    print(
        f"inspection={args.output / 'index.html'} families={len(report['familyAudits'])} "
        f"outfitReady={report['outfitReady']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
