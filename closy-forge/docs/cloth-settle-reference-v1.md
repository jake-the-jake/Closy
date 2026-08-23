# Deterministic Reference Cloth Settle v1

Forge includes a small CPU reference cloth backend for the canonical T-shirt fixture. It is not a production cloth simulator, but it exercises a real deterministic settle path before `actualClothSettleAvailable` is enabled.

## Backend

- Solver ID: `closy.reference_xpbd_cpu.v1`
- Backend: deterministic CPU reference XPBD-style projection
- Fixed step count: `35`
- Solver iterations per step: `6`
- Gravity: `-9.81 m/s^2`
- Damping ratio: from `material.cotton_jersey_reference_v1`
- Collision clearance: `0.006 m`
- Constraint order: stretch, bend, seam, support, collision

The package stores:

- `simulation/rest_state.json`: analytic panel assembly before settle
- `simulation/settled_state.json`: settled positions using the same topology
- `simulation/settle_diagnostics.json`: convergence, penetration, seam residual, strain and energy-proxy diagnostics
- `simulation/simulation_mesh.glb`: settled simulation mesh inspection export

## Current Limits

Self-collision is not implemented in this first reference backend, so packages keep `selfCollisionAvailable: false` and validation reports the warning `self_collision_not_run`.

The solver is tuned for deterministic fixture validation, not final apparel realism. The coarse fan triangulation can produce high maximum strain on skinny neck-band triangles, so convergence uses RMS seam residual, body penetration, finite/inversion checks and percentile/mean strain while still reporting the raw maximum strain.

## Validation Thresholds

Current validator thresholds:

- convergence state must be `converged`
- RMS seam residual must be at most `0.035 m`
- maximum body penetration must be at most `0.012 m`
- non-finite values must be zero
- inverted or degenerate elements must be zero
- settled topology/content hashes must match the simulation mesh manifest

These thresholds are intentionally conservative enough to reject explosions and stale state, while allowing the MVP fixture's coarse seam approximation.
