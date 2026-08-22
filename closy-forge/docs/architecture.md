# Closy Forge Architecture

Closy Forge is an isolated, headless Python project for canonical avatar-and-garment package construction. It is deliberately not part of the Expo bundle and does not import from `src/`, `engine/`, Supabase code, ZeroOne, AI services, or external model providers.

## Repository Boundary

- `src/`: Expo React Native product app. TypeScript-only and mobile-facing.
- `engine/`: separate C++17 rigid avatar/rendering prototype. It is not the Forge pipeline.
- `closy-forge/`: Python 3.11+ deterministic contract and package toolchain.

The boundary between Forge and the app is versioned files: `.closygarment` directories, GLBs, JSON contracts, binary binding files, and reports.

## Product Domain Boundary

Forge only models:

- human avatar contracts, landmarks, body regions, and collision fixtures;
- garment contracts, sewing patterns, seams, meshes, materials, and trims;
- outfit composition metadata in later milestones.

It intentionally does not introduce generic `WorldObject`, `GeneratedObject`, or text-to-anything abstractions.

## Current Pipeline

```text
fixed avatar contract
  -> synthetic metadata-only capture record
  -> deterministic capture quality scoring
  -> synthetic visual observations and empty correction record
  -> semantic T-shirt graph
  -> parametric sewing pattern
  -> simulation-ready panel topology
  -> seam stitch constraints
  -> deterministic CPU reference cloth settle
  -> separate denser render shell
  -> barycentric sim-to-render binding
  -> deterministic .closygarment package
  -> independent validation and reports
```

The current T-shirt stores synthetic metadata-only capture evidence, analytic mask/landmark observations, an empty editable correction record, analytic rest assembly and a deterministic CPU settled state against the fixed collision avatar. The solver exercises gravity, stretch, bend, seam and body-collision constraints, but it is still a reference backend: self-collision, real user images, body scans, learned segmentation, AI inference, ZeroOne processing and personalised body data are not present.

## Future R&D Direction

The next dependency-ready work is deterministic T-shirt parameter fitting from masks/landmarks and richer simulation validation, while preserving the same package boundary. Later work can add reconstruction services, SMPL/SMPL-X research, AI garment proposal adapters, ZeroOne derivatives, and mobile consumption of these packages without changing the package boundary.
