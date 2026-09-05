## Problem and change

The exposed PR65 manual-shell regression missed the unchanged 8 mm rest limit:
four shells were over budget, with a 12.2076 mm maximum. Scalar normal offsets
cannot represent the observed tangential residual. This successor uses bounded
local-frame residuals and a geometry-derived coarse cage, with independent decoding
and rest reconstruction from saved GLB and binding bytes. Broad metric cells receive
bounded geometric refinement; fixture IDs and magic vertex counts are not selectors.

The existing V1 source, 17 thresholds and failed MPC3-09 evidence remain unchanged.
This is `manual_provider_binding_v2_development`, not global C3 or physical validation.

## Results

- 18 packages (nine original shells in two roots), nine deterministic pairs.
- 99/99 baseline states and 44/44 additional states pass; three additional typed
  negative controls pass. All 17 exposed baseline gates pass.
- Serialized rest maximum: 5.809587714e-8 m; motion maximum: 0.016086708 m.
- All three canonical Unit A API probes report unsupported UV lattice explicitly.
  This repair does not yet bind arbitrary canonical/non-grid provider surfaces.
- Saved-artifact publication rechecks inventories and independent reconstruction;
  it cannot convert failed engineering rows into passing claims.

See `docs/evidence/manual_provider_binding_v2_development/report.md`, its result,
package index and publication manifest. Retained low-density development failures
and subsequent refinement are documented in `docs/manual_provider_binding_v2_design.md`.

## Validation and stack

Final local evaluator exited 0 (68.24 s wall, 65.69 s CPU), with unchanged source/input
inventories. Focused binding/package tests: 64 passed. Required remote Forge coverage
is recorded on this exact PR head, not inferred from local passes. The final cumulative
suite belongs to the integrated Unit C head.

Base is Unit A's final pushed head `ac5900f6c3688225d22d6d60e766bb87e5a1d1d0`.
Keep draft, open and unmerged. No Expo, ZeroOne or historical experiment changes.

Initial CI caught absolute host paths in two evidence files. Publication v2 replaces
them with explicit portable projections, preserving the original local receipt hashes
and separate projection digests. The unchanged path-safety check and 43 publication
tests pass. The original failed CI run remains recorded; no binding evaluation rerun.
Windows CI additionally exposed CRLF conversion of the byte-hashed report. A new
evidence-local attributes rule pins only this report to LF; a real `core.autocrlf=true`
index checkout preserves its exact 1731 bytes and SHA-256. No hash tolerance was added.
