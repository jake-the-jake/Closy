# Sim-To-Render Binding Format v1

`binding/sim_to_render.bin` is a fixed-layout little-endian binary file.

## Header

```text
magic:              8 bytes, "CLSYBND1"
version:            uint32, 1
headerSize:         uint32, 96
recordStride:       uint32, 20
recordCount:        uint32
simulationTris:     uint32
panelCount:         uint32
simulationTopoHash: 32 raw bytes
renderTopoHash:     32 raw bytes
```

## Record

Each 20-byte record maps one render vertex to the simulation triangle it came from:

```text
uint32  simulationTriangleIndex
float32 barycentricU
float32 barycentricV
float32 normalOffset
uint16  panelTableIndex
uint16  flags
```

The third barycentric component is `1 - u - v`. Implementation 01 uses zero normal offset because the render shell is deterministic subdivision of the simulation panels. The validator checks magic/version/stride, topology hash agreement, triangle/panel ranges, barycentric ranges, and reconstruction error.

## Production Binding Contract

Phase 6 adds `binding/production_binding_contract.json` beside the binary file. This JSON contract is the stable, inspectable binding authority for the D0 fixed-avatar T-shirt profile. It records:

- source simulation and destination render topology/content hashes;
- stable render vertex IDs in `rv.%06d` form;
- per-render-vertex triangle/barycentric weights;
- logical-to-render split ownership for UV/material/hard-normal boundaries;
- panel, part and opening ownership safeguards;
- deterministic topology invalidation rules.

`reports/production_binding_c3.json` reopens the persisted package files, binary binding and render GLB, validates GLB accessors and expanded geometry, then runs a bounded non-affine motion suite. Its current readiness is `complete_for_d0_fixed_avatar_tshirt_profile` only; it does not promote global Phase 6, clean geometry or canonical geometry.
