# Closy Garment Package v1

`.closygarment` is a directory package for avatar-and-garment assets. It is intentionally inspectable during development; no zip/container format is introduced yet.

Required Implementation 01 tree:

```text
demo_tshirt.closygarment/
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
  reports/*.json
  reports/summary.md
```

The canonical coordinate convention is `closy-rh-yup-plus-z-v1`: metres, right-handed, `+Y` up, semantic `+Z` forward, CCW front-face winding, feet grounded at `Y=0`.

Implementation 01 supports only `garmentClass: "tshirt"`. Unsupported garment classes must be rejected rather than accepted as arbitrary meshes.

The package is valid without ZeroOne, AI reconstruction, source-image textures, personalised avatars, or cloth settle output. Those capabilities are recorded as unavailable until real stages produce them.
