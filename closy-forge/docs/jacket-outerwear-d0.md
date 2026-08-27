# Jacket/Outerwear D0 Public Fixture

This Phase 8 vertical slice exercises a literal open-front outerwear family through the shared
deterministic garment pipeline. It is a project-authored public/synthetic fixture, not a generic
object abstraction or a production jacket asset.

## Literal Construction

- seven panels: split left/right fronts, back, left/right long sleeves and separate left/right
  internal facings;
- twelve physical seams: shoulders, sides, split armholes, underarms and facing attachments;
- five semantic openings: neck, hem, facing-backed front and left/right cuffs;
- the facing outer edges attach to the front panels while their inner edges remain the open-front
  boundary;
- torso and sleeves use explicit outer-shell collision orders, with internal facings immediately
  beneath them;
- no fastening mechanics are claimed.

## Executed D0 Evidence

- bounded 25-candidate fit objective: `0.00156`;
- simulation topology: 331 vertices / 324 triangles;
- dense render shell: 1,944 vertices / 1,296 triangles / 1,944 binding records;
- authored heavy-jersey material preset selected and all four D0 presets executed;
- left/right cuff drift: `0.00004389` / `0.0011949` metres;
- maximum dense seam crack under cuff stress: `0.00788269` metres;
- decoded source/render minimum silhouette IoU: `0.453862146`;
- maximum normalised boundary Chamfer: `0.032568771`;
- canonical 41-file package digest:
  `2ca4a210d560c3452106767dce12c775b9733b9a5e5237d2222026260228101a`.

The cuff stress state is accepted for finite topology, stable openings and bounded seam crack. Its
global energy-convergence flag remains false and is not promoted.

## Limits

This is fixed-avatar CPU evidence. The internal-facing geometry is a bounded reference
approximation, and the open front has no zipper, button or closure simulation. Private-user fitting,
learned inference, measured real-fabric calibration, production GPU cloth, device performance and
production visual acceptance remain not run. Phase 8 remains partial until layered/unusual garment
evidence is implemented.
