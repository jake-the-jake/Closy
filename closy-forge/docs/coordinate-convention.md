# Coordinate Convention

Forge canonical convention:

```text
id: closy-rh-yup-plus-z-v1
units: metres
handedness: right-handed
up axis: +Y
semantic avatar/garment forward: +Z
triangle winding: counter-clockwise when viewed from the front face
ground plane: Y = 0
reference avatar root: midpoint between grounded feet at X = 0, Z = 0
neutral fixture pose: T-pose
```

All canonical hashes are computed after conversion into this convention. Imported assets must declare their source convention and a conversion matrix before they can become canonical.

## Existing Repository Mismatch

Existing avatar documentation trends toward `+Z` forward, while the current production avatar manifest records `forwardAxis: "-Z"` and some GLB runtime paths contain source-axis conversion behaviour. Implementation 01 isolates that mismatch instead of editing mobile assets. Forge fixtures are internally consistent and record the identity conversion matrix in `provenance.json`.

See `adr-0001-coordinate-convention.md` for the accepted architecture decision record.

Implicit centimetre/metre guessing is not allowed. If an imported source omits units or orientation, a future importer must fail validation rather than silently guessing.
