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

## Implementation 01 Pipeline

```text
fixed avatar contract
  -> semantic T-shirt graph
  -> parametric sewing pattern
  -> simulation-ready panel topology
  -> seam stitch constraints
  -> separate denser render shell
  -> barycentric sim-to-render binding
  -> deterministic .closygarment package
  -> independent validation and reports
```

The current T-shirt is analytically assembled. No cloth settle, body scan, image capture, segmentation, AI inference, ZeroOne processing, or personalised body data is present.

## Future R&D Direction

Implementation 02 should keep the same package contract and add deterministic stitch/body-collision settling against the fixed reference avatar. Later work can add reconstruction services, SMPL/SMPL-X research, AI garment proposal adapters, ZeroOne derivatives, and mobile consumption of these packages without changing the package boundary.
