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
proposals/manual_cleanup_preview.glb
proposals/clean_geometry_proposal.json
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
reports/raw_geometry_topology.json
reports/provider_bakeoff.json
reports/geometry_cleanup_plan.json
reports/geometry_cleanup_result.json
reports/clean_geometry_proposal_quality.json
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

Absent optional stages are omitted rather than represented by fake folders. The `source/` directory currently contains deterministic synthetic capture metadata, analytic visual observations, and an empty editable correction record. The `fitting/` directory currently contains a bounded deterministic T-shirt parameter fit from those synthetic observations. The `textures/` directory currently contains texture identity evidence derived from authored render materials, not source photo texture projection. The `proposals/` directory currently contains a package-contained project-authored manual raw visual proposal GLB, a non-canonical cleanup preview GLB, an explicit rejected clean-geometry proposal report, and a provider registry. `reports/raw_geometry_topology.json` records connected-component, boundary-edge, non-manifold and degenerate-triangle diagnostics for the raw GLB. `reports/provider_bakeoff.json` records the Phase 5 D0 provider comparison across the null adapter, selected manual fixture adapter and not-run local open-model boundary; it grants no clean/canonical authority. `reports/geometry_cleanup_plan.json` records deterministic cleanup and repair recommendations derived from those diagnostics. `reports/geometry_cleanup_result.json` records the local safe cleanup adapter result for duplicate-position welding and degenerate-triangle filtering, but it does not run semantic transfer, simulation binding or canonical acceptance. The raw proposal and cleanup preview are accepted only as visual/reference evidence, and the clean proposal report records that clean/canonical acceptance has not been reached. There is no real user imagery, private raster processing, learned segmentation mask, `zeroone/`, accepted clean geometry proposal, external AI mesh execution, or local open-model execution in this milestone.

## Inventory Rules

The manifest inventory uses POSIX package-relative paths only. Absolute paths, `..`, Windows separators, escaping symlinks, undeclared canonical files, and manifest self-hash cycles are invalid.

`manifest.json` and mutable reader reports are excluded from the canonical package digest. All other canonical package files are hashed by SHA-256.

## Capabilities

Capabilities are booleans, not quality scores. Current true states are immutable synthetic capture records, deterministic capture quality scoring, analytic visual observations, editable correction records, synthetic target-garment masks, synthetic T-shirt landmarks, deterministic T-shirt parameter fitting, texture identity evidence, PBR material observations, raw geometry proposal records, raw geometry topology diagnostics, geometry cleanup recommendations, local cleanup execution, provider provenance, provider registry availability, provider contract validation, provider bake-off reporting, manual import adapter declaration, configured manual raw geometry asset, local open-model adapter declaration, geometry proposal quality scoring, pattern, simulation-ready topology, authored material preset, conventional GLB, sim-to-render binding, validated reconstruction, and deterministic reference cloth settle. Source-image texture, external geometry providers, available clean geometry proposal, local open-model execution, personalised avatar, skeleton, self-collision, and ZeroOne states are false. The rejected `proposals/clean_geometry_proposal.json` is evidence that the gate was evaluated, not a claim that a clean proposal exists; the cleanup plan is evidence of required repair work, the cleanup result is evidence of partial preview-only local cleanup, and the provider bake-off is D0 contract/manual-fixture evidence only.
