# Active Blueprint Resume

This is the recoverable checkpoint for continuous Closy master-blueprint execution. It records
literal evidence only; green CI does not by itself promote a global blueprint gate.

## Current State

- Active checkpoint: `PHASE-8-SIMPLE-SKIRT-D0`.
- Branch: `codex/closy-forge-phase-8-simple-skirt`, based on long-sleeved evidence head
  `5fed0c1` from draft PR #11.
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
  283 tests per OS, schema freshness, all four family rebuild/diff/validation paths and the binding
  benchmark.
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

## Current Validation

- Ruff format/lint pass; strict mypy passes across 140 source files.
- 74 schemas are freshly generated.
- Focused family, package, CLI, validator and corruption suites pass.
- The complete local Forge suite passes all 283 collected tests. PR #12 run `32998002569` confirms
  the same simple-skirt matrix on Ubuntu and Windows.
- The sleeveless package has 41 physical files, 37 manifest-inventoried files and 315,015
  inventoried bytes. Two builds have identical file trees and zero validator issues.
- The existing T-shirt package remains byte-identical at 137 files with digest
  `79c5a65deb347bbed23f41c30a926ae00aead7b641fe714d75cb403be8ed07a8`.
- The long-sleeved package has 41 physical files, 37 inventory entries, 441,415 inventoried bytes
  and zero validator issues on both local Python runtimes.
- The simple-skirt package has 41 physical files, 37 inventory entries, 287,245 inventoried bytes
  and zero validator issues on both local Python runtimes.

## Truthful Limits

- Phase 8 is partial globally. Sleeveless, long-sleeved and simple-skirt D0 slices are complete for
  bounded public fixtures; trousers, dresses, shirts, jackets and layered/unusual garments are not
  started.
- Phase 7 and Stage Q remain partial globally. Authored preset execution is not measured real-fabric
  calibration, learned inference, private-user estimation or production GPU cloth.
- The new family uses a fixed synthetic avatar and CPU reference solver. Mobile/device performance,
  provider/private/human tiers, continuous collision and ZeroOne execution remain not run.
- The source/render comparison is a deterministic authored D0 fixture, not production-calibrated
  visual fidelity or clean/canonical garment acceptance.
- Main is visibly unprotected. This is a repository-governance warning, not permission to push or
  merge to main.

## Next Exact Command

After committing and pushing this green PR #12 evidence checkpoint:

```powershell
cd E:\apps\Closy
git switch -c codex/closy-forge-phase-8-simple-trousers
```

## Next Safe Action

Implement a literal simple-trousers family through the shared contracts, with waist/cuff openings,
rise/inseam/outseam semantics, bounded fit, material motion, dense binding, independent fallback,
decoded fidelity and corruption controls. Preserve all three family goldens exactly.
