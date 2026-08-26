# Active Blueprint Resume

This is the recoverable checkpoint for continuous Closy master-blueprint execution. It records
literal evidence only; green CI does not by itself promote a global blueprint gate.

## Current State

- Active checkpoint: `PHASE-7-MATERIAL-PHYSICS-D0`.
- Branch: `codex/closy-forge-phase-7-material-physics`, based on exact green D0 fidelity head
  `91b9ececae3097a42cba45cad90fa81b1ef31d6a` from draft PR #8.
- D0 predecessor final run `32936865331` passed Ubuntu job `98079634048` and Windows job
  `98079633929` with 234 tests per OS, fresh schemas and deterministic package evidence.
- Phase 7 substantive commit `0dbf362a444441d65b10e16d3b30f000294d2b04` is draft PR #9.
- Substantive run `32947979333` passed Ubuntu job `98112789377` and Windows job `98112789618`;
  both jobs passed format, lint, strict type check, 246 tests, 59 fresh schemas, two deterministic
  package builds, package diff, validation/report and the non-canonical binding benchmark.
- Unrelated app edits in `metro.config.js` and `src/features/avatar-*` remain unstaged and must
  be preserved. `closy-forge/.tmp/` remains untracked local evidence only.

## Phase 7 Material Physics

### Descriptor And Selection

- `closy.fabric_physics_descriptor.v1` records thickness, areal density, directional warp/weft
  stretch, shear, bend, damping, friction, collision clearance, restitution, orientation,
  bounded ranges, SI units, confidence and per-field evidence.
- Validation rejects unknown versions, missing/wrong units, non-finite or impossible values,
  contradictory ranges, invalid confidence and undisclosed appearance-only inference.
- `closy.fabric_preset_registry.d0.v1` contains lightweight knit, cotton jersey, heavy jersey and
  lightweight woven public-fixture presets.
- `closy.material_preset_selection.d0.v1` deterministically scores documented cues, preserves all
  alternatives, exposes low confidence, and records explicit overrides. It is not a learned
  classifier or calibrated measurement.

### Calibration And Motion

- Six numerical fixtures independently integrate stretch, shear, bend, damped oscillator,
  gravity sag and floor collision responses. Every persisted result records settings, units,
  qualitative ordering, quantitative values, tolerance and a result hash.
- The reference solver now supports panel-UV-classified warp, weft and shear constraints while
  preserving the prior isotropic default for callers that do not opt into anisotropy.
- Four actual fixed-avatar T-shirt settles run through the existing deterministic CPU solver.
  Each state records convergence, displacement, energy decay, directional strain, seam residual,
  opening stability, body/self collision, topology safety and non-finite counts.
- Render vertices are reconstructed only through the authoritative persisted dense binding path.
  All four bounded executions and reconstructions are finite with zero inverted/degenerate
  triangles.
- Motion-quality acceptance remains false: maximum opening drift ranges from `0.215649759` to
  `0.793515209` metres and unresolved self-collision counts range from 150 to 323. These results
  are evidence to improve, not thresholds to loosen.

## Current Validation

- Ruff passes for the Phase 7 implementation; strict mypy passes across 103 source files.
- 59 schemas are freshly generated.
- The focused descriptor, selector, override, calibration, motion, package corruption, schema and
  coverage suites pass.
- The complete Forge suite passes all 246 collected tests.
- The current package has 137 physical files, 133 manifest-inventoried files and digest
  `79c5a65deb347bbed23f41c30a926ae00aead7b641fe714d75cb403be8ed07a8`.
- Two independent package builds have identical 137-file trees, identical 133-file canonical
  inventories, zero byte differences and the same canonical digest.
- Validation counts are `info=0`, `warning=1`, `error=0`, `fatal=0`; the sole warning is
  `self_collision_unresolved_contacts`.
- The substantive local and Ubuntu/Windows gates are green. The evidence-sync head still requires
  its final remote matrix before Phase 8 branches from it.

## Truthful Limits

- Phase 7 and Stage Q are partial globally. Descriptor validity, deterministic fixture selection
  and bounded numerical execution do not establish measured real-fabric calibration.
- Learned material inference, private-user material estimation, production GPU cloth, continuous
  collision, mobile/device performance, provider/private/human tiers and ZeroOne remain not run.
- D0 motion quality is not accepted because opening stability and self-collision are outside the
  documented bounds. The validator warning remains visible.
- Gate C3 and Phases 3, 4 and 6 remain partial globally. The package remains a project-authored
  public fixture, not a production garment or customer capture.
- Main is visibly unprotected. This is a repository-governance warning, not permission to push or
  merge to main.

## Next Exact Command

After this evidence-sync head is remotely green:

```powershell
cd E:\apps\Closy
git switch -c codex/closy-forge-phase-8-sleeveless-top
```

## Next Safe Action

Push this single evidence-sync commit and confirm its final Ubuntu/Windows matrix, then implement the
truthful sleeveless-top family through the shared pattern, material, settle, binding, fallback,
fitting, texture and fidelity pipeline.
