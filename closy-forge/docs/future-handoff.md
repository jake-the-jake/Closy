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

No source imagery, body scans, or personal measurements are present in Implementation 01.

## ZeroOne

ZeroOne remains optional and downstream. A future ZeroOne bridge can consume validated Forge render/simulation assets and write derivative static or dynamic geometry outputs. Forge packages must remain valid when ZeroOne outputs are absent.

Implementation 01 records:

- `zeroOneStaticAvailable: false`
- `zeroOneDynamicAvailable: false`
- `zeroOne.required: false`

## Recommended Implementation 02

Add a deterministic T-shirt stitch/body-collision/settle stage against `avatar.closy_reference_v1`, preserving the same package tree and adding honest settle reports only after a real solver stage exists.
