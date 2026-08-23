# ADR 0001: Forge Canonical Coordinate Convention

## Status

Accepted for Implementation 01.

## Context

Repository inspection found an existing convention conflict:

- current avatar-oriented documentation trends toward semantic `+Z` forward;
- `assets/models/avatar/production/avatar.manifest.json` declares `forwardAxis: "-Z"`;
- the bundled GLB path includes source-axis conversion behaviour.

Editing the mobile avatar runtime or existing manifests is outside Implementation 01. The Forge package contract needs one internal convention so topology/content hashes are stable and not dependent on runtime import quirks.

## Decision

Forge canonical geometry uses `closy-rh-yup-plus-z-v1`:

- metres;
- right-handed;
- `+Y` up;
- semantic avatar/garment forward is `+Z`;
- counter-clockwise front-face winding;
- ground plane `Y=0`;
- reference avatar root at the midpoint between grounded feet at `X=0`, `Z=0`;
- neutral fixture pose is T-pose.

Every imported future source must declare its source convention and a conversion matrix into this convention before canonical hashes are computed.

## Consequences

- Implementation 01 fixtures are internally consistent.
- Existing mobile avatar files are not changed.
- Future app-runtime migration must explicitly reconcile the current `+Z`/`-Z` mismatch instead of inheriting it silently.
- Implicit centimetre/metre guessing is a validation error for future importers.
