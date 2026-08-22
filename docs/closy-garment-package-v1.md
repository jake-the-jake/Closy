# Closy Garment Package v1

`.closygarment` is a directory package for avatar-and-garment assets. It is intentionally inspectable during development; no zip/container format is introduced yet.

Current deterministic fixture tree:

```text
demo_tshirt.closygarment/
  manifest.json
  provenance.json
  source/capture_record.json
  source/capture_quality.json
  source/visual_observations.json
  source/correction_record.json
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
  reports/*.json
  reports/summary.md
```

The canonical coordinate convention is `closy-rh-yup-plus-z-v1`: metres, right-handed, `+Y` up, semantic `+Z` forward, CCW front-face winding, feet grounded at `Y=0`.

The current Forge fixture supports only `garmentClass: "tshirt"`. Unsupported garment classes must be rejected rather than accepted as arbitrary meshes.

The package is valid without ZeroOne, AI reconstruction, source-image textures or personalised avatars. It now includes synthetic metadata-only capture records, deterministic capture quality scoring, analytic visual observations, an empty editable correction record, and a deterministic CPU reference cloth settle; self-collision, real source textures, and production-grade material calibration remain unavailable until real stages produce them.
