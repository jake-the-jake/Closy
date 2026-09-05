from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from closy_forge.geometry.glb_io import read_glb_meshset
from closy_forge.inspection.cpu_raster import _project, rasterize_settled_garment
from closy_forge.package_io.canonical_json import canonical_dumps, read_json, write_canonical_json
from closy_forge.package_io.hashing import sha256_bytes, sha256_file
from closy_forge.raster import decode_png_rgba, encode_png_rgba

from .registry import family_spec


def capture_roundtrip(package: Path, output: Path) -> dict[str, Any]:
    """Known-geometry synthetic integration, explicitly NOT image parameter estimation.

    Project source samples into panel/vertex addresses. Only depth-visible samples
    are observed; hidden samples are left missing, not invented from the generator.
    """
    manifest = read_json(package / "manifest.json")
    family = manifest["family"]
    mesh = read_glb_meshset(package / "render/fallback.glb")
    output.mkdir(parents=True, exist_ok=True)
    views = []
    panel_ids = {m.panel_id for m in mesh.meshes}
    for label in ("front", "back"):
        rendered = rasterize_settled_garment(
            mesh,
            label=label,
            width=192,
            height=224,
            visible_panel_ids=panel_ids,
            texture_sampler=lambda _p, uv: (
                60 + int(abs(uv[0]) * 100) % 70,
                110 + int(abs(uv[1]) * 80) % 60,
                160,
                255,
            ),
        )
        encoded = encode_png_rgba(rendered.width, rendered.height, rendered.rgba)
        (output / f"{label}.png").write_bytes(encoded)
        decoded = decode_png_rgba(encoded)
        edited = bytearray(decoded.rgba)
        for index in rendered.foreground:
            edited[4 * index] = 230
        (output / f"{label}_pixel_correction.png").write_bytes(
            encode_png_rgba(decoded.width, decoded.height, bytes(edited))
        )
        offset = rendered.camera["frameOffsetPixels"]
        assert isinstance(offset, list)
        samples = []
        for panel in mesh.meshes:
            for vertex_index, vertex in enumerate(panel.vertices):
                x, y, depth = _project(vertex, label, decoded.width, decoded.height, {})
                px = min(decoded.width - 1, max(0, int(round(x + float(offset[0])))))
                py = min(decoded.height - 1, max(0, int(round(y + float(offset[1])))))
                index = py * decoded.width + px
                surface_depth = rendered.depth[index]
                if surface_depth is None or abs(depth - surface_depth) > 0.012:
                    continue
                before = list(decoded.rgba[index * 4 : index * 4 + 4])
                after = list(edited[index * 4 : index * 4 + 4])
                samples.append(
                    {
                        "panelId": panel.panel_id,
                        "vertex": vertex_index,
                        "panelUv": list(panel.panel_uvs[vertex_index]),
                        "sourcePixel": [px, py],
                        "before": before,
                        "after": after,
                    }
                )
        changed = sum(s["before"] != s["after"] for s in samples)
        write_canonical_json(output / f"{label}_panel_projection.json", samples)
        views.append(
            {
                "view": label,
                "sourceSha256": sha256_bytes(encoded),
                "foregroundPixels": len(rendered.foreground),
                "projectedSamples": len(samples),
                "causallyChangedSamples": changed,
                "passed": changed > 0,
                "projectionDigest": sha256_file(output / f"{label}_panel_projection.json"),
            }
        )
    spec = family_spec(family)
    parameters = dict(manifest["parameters"])
    key, changed_value = next(iter(spec.variations[0].items()))
    old_value = parameters[key]
    parameters[key] = changed_value
    corrected = getattr(spec.module("pattern_generator"), spec.pattern_function)(
        spec.parameters(parameters)
    )
    original = read_json(package / "pattern/pattern.json")
    correction = {
        "field": key,
        "before": old_value,
        "after": changed_value,
        "source": "explicit_structured_user_correction_not_pixel_estimate",
        "originalPatternHash": sha256_bytes(canonical_dumps(original).encode()),
        "correctedPatternHash": sha256_bytes(canonical_dumps(corrected).encode()),
        "changed": original != corrected,
        "finite": math.isfinite(float(changed_value)),
    }
    result = {
        "version": "closy.family_capture_roundtrip.development.v1",
        "family": family,
        "packageIdentity": manifest["packageIdentity"],
        "views": views,
        "correction": correction,
        "knownParametersSupplied": True,
        "pixelParameterEstimator": "unsupported_in_this_profile",
        "physicalCaptureEvidence": False,
        "passed": all(v["passed"] for v in views) and correction["changed"],
    }
    write_canonical_json(output / "roundtrip.json", result)
    return result
