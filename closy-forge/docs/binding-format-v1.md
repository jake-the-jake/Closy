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
