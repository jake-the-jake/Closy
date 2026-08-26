# Button-Shirt D0 Public Fixture

This Phase 8 vertical slice proves literal shirt openings and closures through the same deterministic
garment-only contracts used by earlier families. It is not a generic object abstraction.

## Literal Construction

- five panels: left/right split fronts, back, left sleeve and right sleeve;
- ten physical seams: two shoulders, two sides, four split armhole joins and two underarms;
- five semantic openings: neck, hem, front placket and left/right cuffs;
- six monotonically ordered `button_buttonhole` pairs from hem toward neck;
- no physical seam or solver constraint crosses the open placket.

Each closure stores the button panel/edge, buttonhole panel/edge, shared distance from hem, ordinal,
pair status and `simulationEnabled=false`. Corruption tests reject duplicate stations, wrong-side edge
pairing and a placket silently repurposed as a sewn edge.

## Executed D0 Evidence

- bounded 25-candidate fit objective: `0.00156`;
- simulation topology: 256 vertices / 251 triangles;
- dense render shell: 1,506 vertices / 1,004 triangles / 1,506 binding records;
- lightweight-woven selected from authored public-fixture cues;
- four material preset solver states plus cuff-opening stress;
- left/right cuff drift: `0.00002032` / `0.00007738` metres;
- maximum dense seam crack under cuff stress: `0.00247185` metres;
- decoded source/render minimum silhouette IoU: `0.302626779`;
- maximum normalised boundary Chamfer: `0.054750816`;
- canonical package digest: `4805c708f9058b1c0bfe2d298953779402607271ece505fa36d97cfd0f583b91`.

The stress state is accepted for finite topology, non-collapsed cuffs and bounded seam crack, but its
energy convergence flag remains false and is not promoted.

## Limits

This is a deterministic project-authored public/synthetic CPU fixture. Buttons are semantic closure
records, not simulated fastening mechanics. No private-user fitting, learned inference, measured real
fabric, production GPU cloth, mobile/device benchmark, ZeroOne execution or production visual
acceptance is claimed.
