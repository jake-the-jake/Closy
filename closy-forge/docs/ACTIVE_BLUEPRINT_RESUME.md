# Active Blueprint Resume

This is the recoverable checkpoint for continuous Closy master-blueprint execution. It records
literal evidence only; green CI does not by itself promote a global blueprint gate.

## Current State

- Active checkpoint: `PHASE-7-MATERIAL-PHYSICS-D0`.
- Branch: `codex/closy-forge-phase-7-material-physics`, based on exact green D0 fidelity head
  `91b9ececae3097a42cba45cad90fa81b1ef31d6a` from draft PR #8.
- D0 predecessor final run `32936865331` passed Ubuntu job `98079634048` and Windows job
  `98079633929` with 234 tests per OS, fresh schemas and deterministic package evidence.
- Phase 7 substantive commit and remote run are pending; the complete local branch gate is green.
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

## Current Local Validation

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
- The remote Ubuntu/Windows matrix remains to be run before the branch is called green.

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

After the Phase 7 implementation and evidence-sync heads are remotely green:

```powershell
cd E:\apps\Closy
git switch -c codex/closy-forge-phase-8-sleeveless-top
```

## Next Safe Action

Create the Phase 7 substantive commit and stacked draft PR, finish the remote Phase 7 gate targeting
`codex/closy-forge-d0-fidelity-closeout`, then implement the truthful sleeveless-top family through
the shared pattern, material, settle, binding, fallback, fitting, texture and fidelity pipeline.
