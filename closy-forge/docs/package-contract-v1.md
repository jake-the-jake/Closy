# Package Contract v1

Forge writes `.closygarment` as an inspectable directory, not a zip/container file.

## Required Tree

```text
manifest.json
provenance.json
source/capture_record.json
source/capture_quality.json
source/visual_observations.json
source/correction_record.json
fitting/tshirt_fit.json
textures/texture_identity.json
proposals/raw_geometry_proposal.json
proposals/manual_raw_visual_proposal.glb
proposals/provider_registry.json
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
simulation/rest_state.json
simulation/settled_state.json
simulation/settle_diagnostics.json
simulation/material_physics.json
render/fallback.glb
render/mesh_manifest.json
render/materials.json
binding/sim_to_render.bin
binding/binding_manifest.json
reports/avatar_quality.json
reports/capture_quality.json
reports/visual_understanding_quality.json
reports/fitting_quality.json
reports/texture_quality.json
reports/geometry_proposal_quality.json
reports/provider_registry_quality.json
reports/semantic_quality.json
reports/pattern_quality.json
reports/simulation_quality.json
reports/render_quality.json
reports/binding_quality.json
reports/package_validation.json
reports/summary.json
reports/summary.md
```

Absent optional stages are omitted rather than represented by fake folders. The `source/` directory currently contains deterministic synthetic capture metadata, analytic visual observations, and an empty editable correction record. The `fitting/` directory currently contains a bounded deterministic T-shirt parameter fit from those synthetic observations. The `textures/` directory currently contains texture identity evidence derived from authored render materials, not source photo texture projection. The `proposals/` directory currently contains a package-contained project-authored manual raw visual proposal GLB plus a provider registry. The raw proposal is accepted only as visual reference and remains rejected for canonical garment truth. There is no real user imagery, raster source image, learned segmentation mask, `zeroone/`, generated texture atlas, clean geometry proposal, or external AI mesh in this milestone.

## Inventory Rules

The manifest inventory uses POSIX package-relative paths only. Absolute paths, `..`, Windows separators, escaping symlinks, undeclared canonical files, and manifest self-hash cycles are invalid.

`manifest.json` and mutable reader reports are excluded from the canonical package digest. All other canonical package files are hashed by SHA-256.

## Capabilities

Capabilities are booleans, not quality scores. Current true states are immutable synthetic capture records, deterministic capture quality scoring, analytic visual observations, editable correction records, synthetic target-garment masks, synthetic T-shirt landmarks, deterministic T-shirt parameter fitting, texture identity evidence, PBR material observations, raw geometry proposal records, provider provenance, provider registry availability, manual import adapter declaration, configured manual raw geometry asset, geometry proposal quality scoring, pattern, simulation-ready topology, authored material preset, conventional GLB, sim-to-render binding, validated reconstruction, and deterministic reference cloth settle. Source-image texture, generated texture atlas, external geometry providers, clean geometry proposal, personalised avatar, skeleton, self-collision, and ZeroOne states are false.
