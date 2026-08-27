# Active Blueprint Resume

This is the recoverable checkpoint for continuous Closy master-blueprint execution. It records
literal evidence only; green CI does not by itself promote a global blueprint gate.

## Current State

- Active checkpoint: `PHASE-8-JACKET-OUTERWEAR-D0`.
- Branch: `codex/closy-forge-phase-8-jacket-outerwear`, based on button-shirt evidence head
  `f55b2a50080b28c55c28ce7c18474920b19cf3f3` from draft PR #15.
- Phase 7 final run `32949980632` passed Ubuntu job `98118989676` and Windows job `98118989530`
  with 246 tests per OS, 59 fresh schemas and deterministic T-shirt package evidence.
- Phase 8 substantive head `d49227b3e13ba269dfa33b65c7221a54838631d5` is draft PR #10.
- Substantive run `32980095316` passed Ubuntu job `98214343837` and Windows job `98214344137`;
  both jobs passed format, lint, strict type check, 258 tests, 64 fresh schemas, deterministic
  T-shirt and sleeveless package rebuilds, package diffs, validation/report and the non-canonical
  binding benchmark.
- Evidence-sync commit `bffe705785fee3d9d53c7c7cf6f4b5d29b17da45` passed the complete local
  format, lint, strict type, schema, focused and 258-test gates. GitHub did not dispatch an Actions
  suite for either evidence-only synchronization despite matching `closy-forge/**` paths.
- Long-sleeved shared extraction `3741fe3` and substantive implementation `e4841b5` are draft PR
  #11. The complete local gate passes 270 tests, 130 typed source files and 69 fresh schemas.
- PR #11 run `32992270800` passed Ubuntu job `98252504831` and Windows job `98252505317`, including
  270 collected tests per OS, schema freshness, both family rebuild/diff/validation paths and the binding
  benchmark.
- Simple-skirt implementation `80adff0e35375701dc43553dc8b810f924cfface` is draft PR #12.
  The complete local gate passes 283 tests, 140 typed source files and 74 fresh schemas.
- PR #12 run `32998002569` passed Ubuntu job `98272173605` and Windows job `98272174094`, including
  283 collected tests per OS, schema freshness, all four family rebuild/diff/validation paths and the binding
  benchmark.
- Simple-trousers implementation `40fee8ed7106ba7435d40e488c67370d32cab6ee` is draft PR #13.
  The complete local gate passes 295 tests, 150 typed source files and 79 fresh schemas.
- PR #13 run `33007320698` passed Ubuntu job `98304336270` and Windows job `98304336105`, including
  295 tests per OS, schema freshness, all five family rebuild/diff/validation paths and the binding
  benchmark.
- Simple-dress implementation `61c27c4eacfff92dee8d468119277a38e7759fc7` is draft PR #14.
  The complete local gate passes 307 tests, 160 typed source files and 84 fresh schemas.
- PR #14 run `33014572452` passed Ubuntu job `98329331210` and Windows job `98329331018`, including
  307 tests per OS, schema freshness, all six family rebuild/diff/validation paths and the binding
  benchmark.
- Button-shirt implementation `943f0b5d06198c5a97c11cd1121e6244899569ea` is draft PR #15.
  Local Ruff, strict mypy across 170 sources, 89 fresh schemas, the 18-test focused family/
  package/corruption gate and all 322 collected tests pass.
- PR #15 run `33020344545` passed Ubuntu job `98348931958` and Windows job `98348932103`,
  including 322 tests per OS, schema freshness, all seven family rebuild/diff/validation paths and
  the binding benchmark. Both jobs rebuilt the button-shirt package at digest
  `4805c708f9058b1c0bfe2d298953779402607271ece505fa36d97cfd0f583b91`.
- Jacket/outerwear implementation `d79e1b8c725242e65389081a6b0b8c078fd41f9f` is draft PR #16.
  Local Ruff, strict mypy across 180 sources, 94 fresh schemas, the 15-test focused family/
  package/corruption gate and all 337 collected tests pass.
- PR #16 run `33029602357` passed Ubuntu job `98378800026` and Windows job `98378800076`.
  Each job passed 337 tests, rebuilt all predecessor families, and produced identical 41-file
  jacket trees at digest
  `2ca4a210d560c3452106767dce12c775b9733b9a5e5237d2222026260228101a`.
- Unrelated app edits in `metro.config.js` and `src/features/avatar-*` remain unstaged and must
  be preserved. `closy-forge/.tmp/` remains untracked local evidence only.

## Phase 8 Family Verticals

### Sleeveless Top

- `closy.garment_family_ontology.d0.v1` now includes `sleeveless_top` as a garment-specific top,
  not a generic object or an empty-sleeve variant of the T-shirt.
- The pattern has exactly two parametric panels, four seams and four semantic openings: neck,
  hem, left armhole and right armhole. It contains no sleeve or cuff IDs.
- The side/shoulder seam graph resolves with stable IDs and forward/reverse pairing. The assembled
  simulation mesh contains 126 vertices and 124 triangles.
- Pattern triangulation uses the shared family assembly module with an opt-in canonical coordinate
  boundary. The established T-shirt caller remains byte-compatible.

### End-To-End Public Fixture

- A bounded 25-candidate fit executes and accepts objective `0.00182` against authored synthetic
  observations.
- Four Phase 7 material presets execute the actual fixed-avatar CPU solver, authoritative dense
  binding and independent direct-simulation fallback. The dense shell has 744 vertices and 496
  triangles with 744 binding records.
- Underarm/opening stress executes. Both armholes remain non-collapsed; left/right perimeter drift
  is `0.02196083` / `0.00601637` metres and maximum dense seam crack is `0.00182106` metres.
- Two independent raster generators produce decoded source/render evidence. Minimum silhouette IoU
  is `0.274173294`, maximum normalised boundary Chamfer is `0.060037264`, and foreground colour MAE
  is `0.0` for the bounded authored fixture.
- Four decoded mobile-safe PBR PNG maps are persisted with source/generated provenance. This is not
  measured fabric capture or private-user appearance evidence.

### Cross-Platform Determinism Repair

- Initial runs `32960713589`, `32966595179`, `32975153944`, `32976930124` and `32978410880`
  truthfully failed the Ubuntu hardcoded golden while Windows passed.
- Diagnostic inventories isolated sub-ULP panel UV/centre coordinates and reference-avatar
  normal/tangent generation as the only platform-sensitive canonical artifacts.
- Canonical coordinates are now applied at the shared family assembly boundary and to the
  sleeveless package's synthetic avatar copy before GLB frame generation. Solver positions and
  non-physical energy-history diagnostics also have explicit canonical precision.
- Python 3.11 and 3.13 local builds agree byte-for-byte, and the final Ubuntu/Windows run reports
  the same digest `8b4809b5b6be0da3e7018ed6a5c85f29bb613cd1e2142de119132088ca8f0843`.

### Long-Sleeved Top

- Shared typed appearance, material-motion, package-writing and validation contracts replace
  family pipeline cloning while preserving the exact sleeveless digest.
- The literal pattern has front/back torso plus left/right long-sleeve panels, ten shoulder/side/
  armhole/underarm seams and four neck/hem/cuff openings. Armholes are attachments, not openings.
- A bounded 25-candidate fit accepts objective `0.00187`. Four material presets and cuff stress run
  through the CPU solver, 1,248-record dense binding and independent simulation fallback.
- Both cuffs remain non-collapsed; left/right drift is `0.00004436` / `0.0001024` metres and maximum
  dense seam crack is `0.0048587` metres.
- Minimum decoded silhouette IoU is `0.349652973`, maximum normalised boundary Chamfer is
  `0.039093424`, and foreground colour MAE is `0.0`.
- Python 3.11 and 3.13 produce byte-identical 41-file trees at digest
  `35155eb1581219532b6784033358b97f7a6d743db70193f58a48662045674baf`.

### Simple Skirt

- The literal bottom-family pattern has front/back panels, left/right side seams and semantic
  waist/hem openings. It contains no top, sleeve, armhole or cuff semantics.
- A bounded 25-candidate fit accepts objective `0.00122`. Four material presets and waist stress
  execute through the CPU solver, 624-record authoritative dense binding and independent
  106-vertex direct-simulation fallback.
- The waist remains non-collapsed with drift `0.00834621` metres and maximum dense seam crack
  `0.00409052` metres. Stress-solver convergence remains false and is not promoted.
- Minimum decoded silhouette IoU is `0.208469055`, maximum normalised boundary Chamfer is
  `0.064662624`, and foreground colour MAE is `0.0`.
- Python 3.11 and 3.13 produce byte-identical 41-file trees with 37 inventory entries and 287,245
  inventoried bytes at digest
  `c5989b4b0d164aebd866fe98eaa9fed85477d73f23d55eead05e04a14a7ae2df`.

### Simple Trousers

- The literal bottom-family pattern has four front/back half-leg panels, paired outseams and
  inseams, front/back rise seams, one waist opening and separate left/right cuff openings.
- A bounded 25-candidate fit accepts objective `0.00138`. Four material presets and two-cuff stress
  execute through the CPU solver, 1,092-record authoritative dense binding and independent
  186-vertex direct-simulation fallback.
- Both cuffs remain non-collapsed; left/right drift is `0.0014164` / `0.00258537` metres and maximum
  dense seam crack is `0.00708721` metres. Stress-solver convergence remains false and is not
  promoted.
- Composite-panel source fixtures and independent raster output record minimum decoded silhouette
  IoU `0.26662234`, maximum normalised boundary Chamfer `0.048480955`, and colour MAE `0.0`.
- Python 3.11 and 3.13 produce byte-identical 41-file trees with 37 inventory entries and 410,405
  inventoried bytes at digest
  `4c023d82785791335d966fe81e64928fdbe646e47c7d60786c8666eed4e9a886`.

### Simple Dress

- The literal one-piece pattern has separate front/back bodices and skirts, eight shoulder/side/
  waist seams, and semantic neck/hem/left-armhole/right-armhole openings. The waist is sewn rather
  than falsely represented as an opening.
- A bounded 25-candidate fit accepts objective `0.0012`. Four material presets and armhole stress
  execute through the CPU solver, 1,134-record authoritative dense binding and independent
  193-vertex direct-simulation fallback.
- Both armholes remain non-collapsed; left/right drift is `0.00544586` / `0.00110252` metres and
  maximum dense seam crack is `0.00736142` metres. Stress-solver convergence remains false and is
  not promoted.
- Composite bodice/skirt source fixtures and independent raster output record minimum decoded
  silhouette IoU `0.50009176`, maximum normalised boundary Chamfer `0.029052881`, and colour MAE
  `0.0`.
- Python 3.11 and 3.13 produce byte-identical 41-file trees with 37 inventory entries and 412,888
  inventoried bytes at digest
  `e8b1a3c00d9276c9d95ee2525bf3e24c88a84ee4ab03a5f5472e73175663b00a`.

### Button Shirt

- The literal top-family pattern has split left/right fronts, one back and two sleeves. Ten physical
  shoulder/side/armhole/underarm seams leave neck, hem, front placket and both cuffs open.
- Six ordered closure stations pair buttons on the right placket with buttonholes on the left.
  Closure records are semantic and openable but deliberately do not become solver constraints.
- A bounded 25-candidate fit accepts objective `0.00156`. Four material presets execute and the
  authored cues select `material.lightweight_woven_d0_v1` for the settled package state.
- Both cuffs remain non-collapsed under opening stress; left/right drift is `0.00002032` /
  `0.00007738` metres and maximum dense seam crack is `0.00247185` metres. Stress convergence is
  false and is not promoted.
- The authoritative dense path has 1,506 binding records; the independent fallback retains 256
  simulation vertices. Decoded source/render comparison records minimum IoU `0.302626779`, maximum
  normalised boundary Chamfer `0.054750816`, and colour MAE `0.0`.
- Repeated local builds produce matching 41-file trees with 37 inventory entries, 495,639 bytes and
  digest `4805c708f9058b1c0bfe2d298953779402607271ece505fa36d97cfd0f583b91`.

### Jacket/Outerwear

- The literal outerwear pattern has split left/right fronts, one back, two long sleeves and
  separate left/right internal facings. Twelve physical seams include two facing attachments.
- Facing outer edges attach to the front panels while facing inner edges form the open-front
  boundary. Torso/sleeves and internal facings carry explicit outer-shell collision order.
- A bounded 25-candidate fit accepts objective `0.00156`. Four material presets execute and the
  authored fixture selects `material.heavy_jersey_d0_v1`.
- Both cuffs remain non-collapsed under opening stress; left/right drift is `0.00004389` /
  `0.0011949` metres and maximum dense seam crack is `0.00788269` metres. Stress convergence is
  false and is not promoted.
- The authoritative dense path has 1,944 binding records; the independent fallback retains 331
  simulation vertices. Decoded source/render comparison records minimum IoU `0.453862146`, maximum
  normalised boundary Chamfer `0.032568771`, and colour MAE `0.0`.
- Repeated local, Ubuntu and Windows builds produce matching 41-file trees with 37 inventory
  entries, 583,414 bytes and digest
  `2ca4a210d560c3452106767dce12c775b9733b9a5e5237d2222026260228101a`.

## Current Validation

- Ruff format/lint pass; strict mypy passes across 180 source files.
- 94 schemas are freshly generated.
- Focused family, package, CLI, validator and corruption suites pass.
- The complete local Forge suite passes all 337 collected tests in `3082.10s`. PR #16 run
  `33029602357` confirms the same eight-family matrix on Ubuntu and Windows Python 3.11.
- The sleeveless package has 41 physical files, 37 manifest-inventoried files and 315,015
  inventoried bytes. Two builds have identical file trees and zero validator issues.
- The existing T-shirt package remains byte-identical at 137 files with digest
  `79c5a65deb347bbed23f41c30a926ae00aead7b641fe714d75cb403be8ed07a8`.
- The long-sleeved package has 41 physical files, 37 inventory entries, 441,415 inventoried bytes
  and zero validator issues on both local Python runtimes.
- The simple-skirt package has 41 physical files, 37 inventory entries, 287,245 inventoried bytes
  and zero validator issues on both local Python runtimes.
- The simple-trousers package has 41 physical files, 37 inventory entries, 410,405 inventoried
  bytes and zero validator issues on both local Python runtimes.
- The simple-dress package has 41 physical files, 37 inventory entries, 412,888 inventoried bytes
  and zero validator issues on both local Python runtimes.
- The button-shirt package has 41 physical files, 37 inventory entries, 495,639 inventoried bytes
  and zero validator issues in repeated local and cross-OS builds.
- The jacket package has 41 physical files, 37 inventory entries, 583,414 inventoried bytes and
  zero validator issues in repeated local and cross-OS builds.

## Truthful Limits

- Phase 8 is partial globally. Sleeveless, long-sleeved, simple-skirt, simple-trousers,
  simple-dress, button-shirt and jacket/outerwear D0 slices are complete for bounded public
  fixtures; layered/unusual garments are not started.
- Phase 7 and Stage Q remain partial globally. Authored preset execution is not measured real-fabric
  calibration, learned inference, private-user estimation or production GPU cloth.
- The new family uses a fixed synthetic avatar and CPU reference solver. Mobile/device performance,
  provider/private/human tiers, continuous collision and ZeroOne execution remain not run.
- The source/render comparison is a deterministic authored D0 fixture, not production-calibrated
  visual fidelity or clean/canonical garment acceptance.
- Main is visibly unprotected. This is a repository-governance warning, not permission to push or
  merge to main.

## Next Exact Command

After PR #16 cross-OS evidence is green and truth-synced:

```powershell
cd E:\apps\Closy
git switch -c codex/closy-forge-phase-8-layered-unusual
```

## Next Safe Action

Implement one literal layered/unusual garment fixture through the shared contracts with explicit
inner/outer layer identity, deterministic collision order and bounded inter-layer motion evidence.
Preserve all seven completed Phase 8 family goldens and keep Phase 8 globally partial unless that
final family scope is fully literal.
