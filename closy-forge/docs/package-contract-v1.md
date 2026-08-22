# Package Contract v1

Implementation 01 writes `.closygarment` as an inspectable directory, not a zip/container file.

## Required Tree

```text
manifest.json
provenance.json
avatar/avatar_contract.json
avatar/reference_avatar.glb
avatar/collision.glb
avatar/body_regions.json
semantic/garment_graph.json
semantic/confidence.json
pattern/pattern.json
pattern/panels.svg
simulation/simulation_mesh.glb
simulation/mesh_manifest.json
simulation/constraints.json
simulation/material_physics.json
render/fallback.glb
render/mesh_manifest.json
render/materials.json
binding/sim_to_render.bin
binding/binding_manifest.json
reports/avatar_quality.json
reports/semantic_quality.json
reports/pattern_quality.json
reports/simulation_quality.json
reports/render_quality.json
reports/binding_quality.json
reports/package_validation.json
reports/summary.json
reports/summary.md
```

Absent optional stages are omitted rather than represented by fake folders. There is no `source/`, `zeroone/`, `textures/`, capture, segmentation, or AI report in this milestone.

## Inventory Rules

The manifest inventory uses POSIX package-relative paths only. Absolute paths, `..`, Windows separators, escaping symlinks, undeclared canonical files, and manifest self-hash cycles are invalid.

`manifest.json` and mutable reader reports are excluded from the canonical package digest. All other canonical package files are hashed by SHA-256.

## Capabilities

Capabilities are booleans, not quality scores. Current true states are pattern, simulation-ready topology, authored material preset, conventional GLB, sim-to-render binding, and validated reconstruction. Cloth settle, source-image texture, personalised avatar, skeleton, and ZeroOne states are false.
