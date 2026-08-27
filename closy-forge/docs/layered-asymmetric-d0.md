# Layered Asymmetric D0 Public Fixture

This Phase 8 vertical slice exercises a literal two-layer asymmetric tunic through the shared
deterministic garment pipeline. It is a project-authored public/synthetic fixture, not generic
object generation, production cloth, or private-user fitting.

## Literal Construction

- four non-empty panels: inner front/back and outer front/back;
- eight physical seams: shoulder and side pairs for each layer;
- eight semantic openings: neck, hem and left/right armholes for each layer;
- an inner cotton-jersey base layer at collision order `10` and an outer lightweight-woven layer
  at collision order `20`;
- inter-layer collision is explicitly enabled with `0.014 m` minimum declared clearance and
  `0.020 m` measured front rest clearance;
- the outer front/back hems have a literal `0.090 m` left-to-right drop;
- no empty sleeve, cuff, button, or generic-object semantics are retained.

## Executed D0 Evidence

- bounded 25-candidate fit objective: `0.00182`;
- simulation topology: 258 vertices / 254 triangles;
- dense render shell: 1,524 vertices / 1,016 triangles / 1,524 binding records;
- all four D0 material presets execute through the CPU solver;
- all four layer-specific armholes remain non-collapsed under stress;
- maximum dense seam crack under opening stress: `0.0079439 m`;
- decoded source/render minimum silhouette IoU: `0.394545455`;
- maximum normalised boundary Chamfer: `0.058526042`;
- repeated local builds are byte-identical across 41 physical files and 37 canonical inventory
  entries at digest `24ddc94e37e9b2cee3f1118b57df9ca233b9dec3815a075a9ca161ffd0523417`.

## Limits

The layer clearance is a bounded reference construction, not production-grade multilayer cloth or
continuous collision. The visual evidence covers the outer shell from authored front/back cameras;
it is not private capture, human review, or product-calibrated fidelity. Button mechanics,
measured real-fabric calibration, learned inference, production GPU motion, mobile performance and
ZeroOne execution remain not run. The listed Phase 8 D0 family ladder is now literal, while global
Phase 8 remains partial under those production and private-evidence requirements.
