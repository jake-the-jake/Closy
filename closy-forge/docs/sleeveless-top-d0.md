# Sleeveless Top D0

Phase 8 begins with one literal additional garment family. The fixture is project-authored,
synthetic and deterministic. Completing this bounded slice does not complete Phase 8 globally.

## Family Contract

The canonical pattern contains two parametric torso panels. Stable IDs represent front/back
panels, left/right shoulder seams, left/right side seams, neck, hem and left/right armholes. No
sleeve or cuff entity is represented with empty geometry. Shared assembly helpers perform panel
triangulation and seam/opening resolution; family modules retain the parameters, ontology,
fitting, motion and appearance policy.

## Executed Fixture

`closy-forge demo build-sleeveless` executes:

- a bounded 25-candidate fit against authored width, length and armhole observations;
- deterministic pattern sampling, triangulation and side/shoulder constraint construction;
- all four Phase 7 material presets through the fixed-avatar CPU reference solver;
- a separate `opening_stress` motion state and armhole-retention measurement;
- dense render reconstruction through `binding/sim_to_render.bin`;
- a direct simulation-topology fallback that never invokes the dense binding;
- conventional indexed GLBs with normals, VEC4 tangents and UVs;
- two source rasters from a pattern-boundary scanline generator;
- two rendered rasters from the independent CPU triangle renderer;
- four decoded mobile-safe PBR maps and decoded source/render metrics.

The validator independently reloads persisted GLBs and the binary binding, rejects out-of-simplex
records, reconstructs dense vertices, verifies the direct fallback topology, decodes every PNG,
and recomputes inventory hashes/digest. Corruption tests cover wrong family identity, wrong
semantic IDs, refreshed motion claims and binary binding damage.

## Evidence Boundary

- Sleeveless-top D0 vertical slice: complete when package validation and deterministic CI pass.
- Phase 8 globally: partial.
- Next family: long-sleeved top.
- Skirts, trousers, dresses, shirts, jackets and layered/unusual garments: not started.
- Learned/private fitting, measured real-fabric calibration, GPU cloth, mobile/device performance,
  provider geometry, human visual acceptance and production fidelity: not run.

The reference avatar is fixed and synthetic. The decoded PBR maps are authored/derived D0 maps,
not measured fabric capture. Underarm stress is a bounded reference-solver test, not production
cloth certification.
