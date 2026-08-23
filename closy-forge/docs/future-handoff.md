# Future Reconstruction And ZeroOne Handoff

Future reconstruction services should produce the same package contract, not a parallel generic object format.

## Reconstruction Service Boundary

A future service may add capture, segmentation, learned garment proposal, texture recovery, or SMPL-family avatar fitting, but its output must still resolve to:

```text
AvatarContract
GarmentSemanticGraph
PatternPanel / GarmentSeam / Opening
GarmentSimulationMesh
GarmentRenderShell
GarmentRenderBinding
```

No real source imagery, body scans, or personal measurements are present in the current deterministic fixture. The current `source/` records are synthetic metadata-only capture fixtures used to test privacy, provenance and quality gates before real media ingestion exists.

## ZeroOne

ZeroOne remains optional and downstream. A future ZeroOne bridge can consume validated Forge render/simulation assets and write derivative static or dynamic geometry outputs. Forge packages must remain valid when ZeroOne outputs are absent.

The current deterministic fixture records:

- `zeroOneStaticAvailable: false`
- `zeroOneDynamicAvailable: false`
- `zeroOne.required: false`

## Next Implementation Direction

Continue into BP-48 persisted normals, glTF tangents and richer pose/motion validation while improving simulation diagnostics. Synthetic capture, visual-observation, deterministic fitting and BP-47 SVG inspection artifacts now exist, but real image ingestion, learned segmentation, source/provider visual-fidelity evidence, self-collision and production-grade material calibration remain explicitly unavailable.
