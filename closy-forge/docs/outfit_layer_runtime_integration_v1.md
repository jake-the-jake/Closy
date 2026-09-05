# Actual Package Outfit Integration V1

This is a new, explicit Forge development lane. It does not change Expo, the old
layered-asymmetric validator, historical physics/capture experiments or ZeroOne.
Canonical garment authority remains with Closy panels, seams, simulation and binding.

## Assembly And Contact

`package_layering_v1.load_layers()` validates real successor family packages,
reference-avatar compatibility, units, layer IDs/order, material fields and bindings.
`combine()` copies actual simulation/render panels and renumbers existing bindings.
It never substitutes radial rings or rebinds each posed state. Layer/panel identity
is deterministic under input permutation; cross-part bindings reject explicitly.

The four states are existing analytic garment drivers: neutral, reach-left,
twist-right and step-left. They are not skeletal-avatar or cloth dynamics tests.
All participating layers advance in one bounded Jacobi correction loop. Broad-phase
triangle bounds feed vertex/triangle and edge/edge proximity, edge-through-face
crossing and coplanar-overlap tests, including nonmatching tessellations.

Each layer contributes thickness, clearance, areal density and body clearance.
Thickness/clearance set contact separation; density and triangle area set inverse
mass weights. Corrections are bounded to 4 mm per step and 45 mm total. Existing
distance/seam constraints remain active. Local orientation guards protect both
previous-step area and the posed-input normal hemisphere. Twelve iterations are
the default, not a claim of physical convergence. Per-layer fabric calibration,
friction and anisotropic dynamics are not implemented.

Local tuck policy affects correction/order, never detection. Blocked contacts remain
reported. Crossing depth is a conservative normal-interval deficit, not a signed
volume penetration measurement. Witness positions are representative triangle/contact
locations; discrete snapshots and 30 midpoint contact queries do not establish CCD.

After correction the producer serializes cages and reconstructed dense meshes,
regenerates frames/bounds and independently rereads all data. Readiness requires
contact/body residual <=0.16 mm, paired seam gap <=8 mm, opening length drift <=10%,
zero inversions, displacement <=45 mm and binding error <=2 micrometres. Failure
keeps a readable output and reports `verified_input_only_not_collision_ready`;
that input is not falsely described as a collision-free outfit.

## Integrity And Runtime

The trusted-manifest loader checks an exact inventory, byte sizes/hashes, non-link
paths, both binding topology hashes, bounded weights/counts/semantics, and canonical
vertex/triangle layer ownership. Before/after contacts, full witnesses and opening/
seam measurements are recomputed. Rehashed reports cannot erase known contacts.
The focused review's historical failures and repairs remain in
[the security review](package_layering_v1_review.md).

Runtime V3 delivers actual A, B and whole-outfit geometry through the unchanged V2
page codec with a new trusted metadata envelope. Source, garment, avatar, profile and
provenance must agree. Prefix availability requires decoded valid geometry, not a
GLB header. Same-size cross-package injection, wrong-size chunks and truncated
reception are distinct controls. See [runtime details](runtime_delivery_v3.md).

Runtime success only certifies encoding, decoding, integrity and binding fidelity.
The representative outfit's `sourceQuality.fitReady` is retained even when false.
No mobile, personalized-avatar, dynamic ZeroOne or physical fabric acceptance follows.

## Inspection Command

From `E:/apps/Closy-all-family-layer-integration-v1/closy-forge`:

```powershell
$env:PYTHONPATH = 'src'
py -3.11 scripts/demo_family_outfit_v1.py --families-cache .tmp/family-final-v2/build1 --output .tmp/demo-final-v1
```

Use a fresh output directory. The optional cache is validated by package hashes and
the actual compiler import closure; without it the command builds all nine nominal
garments. Output includes `index.html`, `report.json`, conventional `garments/*/render/
fallback.glb`, `outfit/render.glb` and `inspection/*.png`. Exit 0 means geometry and
inspection completed, not that the outfit passed its fit budgets. Read `outfitReady`.

Images are CPU rasters of actual serialized meshes. The collapsed-sleeve before view
uses retained exact failed-triangle witnesses, not an invented original model. The
binding before view reconstructs the saved PR65 cage/binding; the after view uses
the new decoded local-frame binding. No generated visuals or human-photo claims.

Optional static commands require a short fresh Windows output root; otherwise the
existing processor can exceed its cache path limit. See [static instructions and
the retained failed attempt](static_family_v3.md). ZeroOne remains optional and read-only.
