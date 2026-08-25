# Deterministic Reference Cloth Settle v1.2

Forge includes a small CPU reference cloth backend for the canonical T-shirt fixture. It is not a production cloth simulator, but it exercises a real deterministic settle path before `actualClothSettleAvailable` is enabled.

## Backend

- Solver ID: `closy.reference_xpbd_cpu.v1.2_self_collision_d0`
- Backend: deterministic CPU reference XPBD-style projection
- Fixed step count: `35`
- Solver iterations per step: `6`
- Gravity: `-9.81 m/s^2`
- Damping ratio: from `material.cotton_jersey_reference_v1`
- Collision clearance: `0.006 m`
- Fixture support stiffness: `0.03`
- Neck-band seam target cap: `0.02 m`
- Constraint order: stretch, bend, seam, support, body collision, D0 self-collision

The package stores:

- `simulation/rest_state.json`: analytic panel assembly before settle
- `simulation/settled_state.json`: settled positions using the same topology
- `simulation/settle_diagnostics.json`: convergence, penetration, seam residual, strain and energy-proxy diagnostics
- `simulation/simulation_mesh.glb`: settled simulation mesh inspection export
- `reports/self_collision_report.json`: D0 reference self-collision evidence, adversarial fixtures and unresolved-contact metrics

## Current Limits

Self-collision now runs as a deterministic D0 reference vertex/triangle pass. Packages set `selfCollisionAvailable: true` and `selfCollisionEvidenceAvailable: true`; validation rejects stale or contradictory reports. The current coarse fixed-avatar T-shirt fixture still retains unresolved reference contacts, so validation reports the warning `self_collision_unresolved_contacts` rather than the old `self_collision_not_run` placeholder.

This is not a production GPU collision backend. High-velocity continuous collision/tunnelling is explicitly unsupported and recorded as `unsupported_high_velocity_tunnelling`.

The solver is tuned for deterministic fixture validation, not final apparel realism. The v1.2 fixture policy softens high-y/neck-band support tethers, tightens the neck-band target length and runs a bounded reference self-collision projection so seam correspondence evidence reflects the ordered seam construction instead of artificial support drift. The coarse fan triangulation can still produce high maximum strain on skinny neck-band triangles, so convergence uses RMS seam residual, body penetration, finite/inversion checks and percentile/mean strain while still reporting the raw maximum strain.

## Validation Thresholds

Current validator thresholds:

- convergence state must be `converged`
- RMS seam residual must be at most `0.035 m`
- maximum body penetration must be at most `0.012 m`
- non-finite values must be zero
- inverted or degenerate elements must be zero
- settled topology/content hashes must match the simulation mesh manifest

These thresholds are intentionally conservative enough to reject explosions and stale state, while allowing the MVP fixture's coarse seam approximation.
