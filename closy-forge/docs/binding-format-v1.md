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

- the authoritative `settled_simulation_to_subdivided_render_v1` route and deprecated predecessor tracks;
- source simulation and destination render topology/content hashes;
- stable render vertex IDs in `rv.%06d` form;
- per-render-vertex triangle/barycentric weights;
- logical-to-render split ownership for UV/material/hard-normal boundaries;
- panel, part and opening ownership safeguards;
- deterministic topology invalidation rules.

`simulation/motion_states/index.json` indexes eleven solver-produced states. Each state stores simulation positions and provenance; dense reconstruction is generated only by decoding `binding/sim_to_render.bin` after the package is reopened. `render/simulation_fallback.glb` is a genuinely separate direct simulation-mesh representation and does not invoke dense reconstruction. Shared panel centroids and silhouette bounds are compared because the two representations have different topology.

`reports/production_binding_c3.json` reopens persisted package files, binding bytes, motion-state bytes and both GLBs before recomputing the evidence. It separately records seam crack residual beyond intended separation, seam-frame tangential sliding and all four semantic-opening drifts. Normals and VEC4 tangents are reconstructed and validated for dense and fallback output. The current readiness is truthfully `partial_scoped_reference_profile`: persisted validation passes, but fallback landmark agreement and tangential sliding exceed their provisional scale-derived thresholds. Global Phase 6, clean geometry and canonical geometry remain false.

Host CPU timings are deliberately excluded from the canonical package. Use `closy-forge benchmark binding-c3 PACKAGE --output REPORT --warmups 3 --repeats 20 --commit-sha SHA` to produce a schema-validated, noncanonical report with dense and fallback measurements, host/runtime identity and `tracemalloc` peak memory.
