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
simulation/motion_states/index.json
simulation/motion_states/*.json
render/fallback.glb
render/simulation_fallback.glb
render/simulation_fallback_manifest.json
render/mesh_manifest.json
render/materials.json
binding/sim_to_render.bin
binding/binding_manifest.json
binding/production_binding_contract.json
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
reports/production_binding_c3.json
reports/self_collision_report.json
reports/package_validation.json
reports/summary.json
reports/summary.md
```

Absent optional stages are omitted rather than represented by fake folders. The `source/` directory currently contains deterministic synthetic capture metadata, analytic visual observations, and an empty editable correction record. The `fitting/` directory currently contains a bounded deterministic T-shirt parameter fit from those synthetic observations. The `textures/` directory currently contains texture identity evidence derived from authored render materials, not source photo texture projection. The `proposals/` directory currently contains a package-contained project-authored manual raw visual proposal GLB, a non-canonical cleanup preview GLB, an explicit rejected clean-geometry proposal report, and a provider registry. `reports/raw_geometry_topology.json` records connected-component, boundary-edge, non-manifold and degenerate-triangle diagnostics for the raw GLB. `reports/provider_bakeoff.json` records the Phase 5 D0 provider comparison across the null adapter, selected manual fixture adapter and not-run local open-model boundary; it grants no clean/canonical authority. `binding/production_binding_contract.json` identifies one authoritative settled-simulation-to-subdivided-render route and deprecates contradictory legacy tracks. `simulation/motion_states/` stores eleven solver-produced source states. `render/simulation_fallback.glb` is the independent direct simulation-mesh fallback. `reports/production_binding_c3.json` reopens and recomputes all of those persisted assets; its current status is `partial_scoped_reference_profile`, because fallback landmark agreement and tangential seam sliding still exceed provisional thresholds. Global Phase 6, clean proposal and canonical geometry remain false. `reports/self_collision_report.json` records integrated deterministic D0 collision projections, independent-oracle/adversarial fixtures, unresolved contacts and the explicit high-velocity tunnelling limitation. There is no real user imagery, private raster processing, learned segmentation model, `zeroone/`, accepted clean geometry proposal, external AI mesh execution, or local open-model execution in this milestone.

## Inventory Rules

The manifest inventory uses POSIX package-relative paths only. Absolute paths, `..`, Windows separators, escaping symlinks, undeclared canonical files, and manifest self-hash cycles are invalid.

`manifest.json` and mutable reader reports are excluded from the canonical package digest. All other canonical package files are hashed by SHA-256.

## Capabilities

Capabilities are booleans, not quality scores. `productionBindingC3EvidenceAvailable` means the package contains recomputable evidence; `productionBindingC3ProfileAvailable` remains false until every literal scoped threshold passes. Source-image texture, external geometry providers, available clean geometry proposal, local open-model execution, personalised avatar, skeleton, production GPU self-collision, global Phase 6 completion and ZeroOne states are false. The rejected clean proposal, partial cleanup result, provider bake-off and partial C3 report are evidence that their gates were evaluated, not claims of canonical acceptance.

Host-dependent performance measurements are never canonical package files. The benchmark schema is exported as `schemas/v1/production-binding-benchmark.schema.json`; reports belong in local or CI run evidence and must include commit, host/runtime identity, warmups, repeats, dense/fallback timings, peak-memory method and limitations.
