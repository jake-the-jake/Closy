# Deterministic Reference Cloth Settle v1.3

Forge includes a small CPU reference cloth backend for the canonical T-shirt fixture. It is not a production cloth simulator, but it exercises a real deterministic settle path before `actualClothSettleAvailable` is enabled.

## Backend

- Solver ID: `closy.reference_xpbd_cpu.v1.3_integrated_self_collision_d0`
- Backend: deterministic CPU reference XPBD-style projection
- Fixed step count: `35`
- Solver iterations per step: `6`
- Gravity: `-9.81 m/s^2`
- Damping and bounded warp/weft/shear/bend coefficients: selected Phase 7 descriptor
- Collision clearance: `0.006 m`
- Fixture support stiffness: `0.03`
- Neck-band seam target cap: `0.02 m`
- Constraint order: panel-UV-classified warp/weft/shear stretch, bend, seam, support, body collision, then bounded D0 self-collision projections

The package stores:

- `simulation/rest_state.json`: analytic panel assembly before settle
- `simulation/settled_state.json`: settled positions using the same topology
- `simulation/settle_diagnostics.json`: convergence, penetration, seam residual, strain and energy-proxy diagnostics
- `simulation/simulation_mesh.glb`: settled simulation mesh inspection export
- `reports/self_collision_report.json`: D0 reference self-collision evidence, adversarial fixtures and unresolved-contact metrics
- `simulation/motion_states/index.json`: index and hashes for eleven bounded solver-produced deformation states
- `simulation/motion_states/*.json`: persisted positions, settings, material parameters, convergence diagnostics and provenance for each state
- `simulation/material_presets.json`: four authored descriptors with SI fields, ranges and provenance
- `simulation/material_motion_states/*.json`: actual settle output for each Phase 7 preset
- `reports/material_calibration.json`: six isolated numerical parameter-response fixtures
- `reports/material_motion_suite.json`: cross-preset motion and dense-binding evidence

## Current Limits

Self-collision now runs as a deterministic D0 vertex-triangle and edge-edge reference pass integrated at bounded solver checkpoints. Its broad-phase audit uses an independent exact-proximity subset oracle rather than the same AABB predicate. Packages set `selfCollisionAvailable: true` and `selfCollisionEvidenceAvailable: true`; validation rejects stale or contradictory reports. Per-iteration unresolved-contact and penetration histories are recorded, together with monotonicity and topology-safety flags. The current coarse fixed-avatar T-shirt fixture still retains unresolved reference contacts, so validation reports `self_collision_unresolved_contacts` rather than hiding the limitation.

This is not a production GPU collision backend. A bounded deterministic swept-collision fixture
suite covers high-velocity crossing, thin-layer approach, opening-boundary crossing, and
fail-closed motion beyond the configured substep bound. That fixture suite is not integrated into
the reference motion solver's response loop. Packages therefore record
`bounded_ccd_not_integrated_into_reference_motion_solver`; the solver diagnostics retain
`unsupported_high_velocity_tunnelling` to describe that narrower integration limitation.

The solver is tuned for deterministic fixture validation, not final apparel realism. The v1.3 fixture policy softens high-y/neck-band support tethers, tightens the neck-band target length and performs bounded collision projection during the solve. The coarse fan triangulation can still produce high maximum strain on skinny neck-band triangles, so convergence uses RMS seam residual, body penetration, finite/inversion checks and percentile/mean strain while still reporting the raw maximum strain.

## Validation Thresholds

Current validator thresholds:

- convergence state must be `converged`
- RMS seam residual must be at most `0.035 m`
- maximum body penetration must be at most `0.012 m`
- non-finite values must be zero
- inverted or degenerate elements must be zero
- settled topology/content hashes must match the simulation mesh manifest

These thresholds are intentionally conservative enough to reject explosions and stale state, while allowing the MVP fixture's coarse seam approximation.
