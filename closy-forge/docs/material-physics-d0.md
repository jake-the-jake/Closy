# Material Physics D0

Phase 7 adds a bounded public-fixture material contract. It is not measured-fabric calibration or
a learned material estimator.

## Descriptor

`closy.fabric_physics_descriptor.v1` stores thickness, areal density, directional warp/weft
stretch stiffness, shear, bend, damping, friction, collision clearance, optional restitution and
warp orientation. Every physical field carries an SI unit, allowed range, confidence and evidence
source. Validation fails closed on unknown versions, invalid units, non-finite or impossible
values, contradictory ranges and undisclosed appearance-only inference.

The D0 registry contains lightweight knit, cotton jersey, heavy jersey and lightweight woven.
Values are deterministic project-authored fixture presets, not laboratory measurements.

## Selection

The selector compares documented categorical observations with all four profiles using an
equal-weight deterministic score. Its report persists matched/mismatched cues, every alternative,
score margin, confidence state and an optional explicit override record. No learned classifier is
declared or executed.

## Calibration Fixtures

Six small CPU simulations isolate stretch, shear, bending, damping, gravity sag and floor
collision. Each varies one parameter over low/base/high values, integrates a response, records the
quantitative result and checks only the expected qualitative ordering. Result hashes cover the
measured response and settings; the expected result is not copied from the input coefficient.

## Synthetic Mechanical Calibration v2

`reports/synthetic_mechanical_calibration.json` adds an inverse-calibration exercise over all four
authored presets. Ten descriptor fields each produce three calibration observations and two unseen
synthetic holdouts, for 120 calibration and 80 holdout observations. A bounded 2,049-candidate
grid estimates each field from response values without receiving the authored truth as an input.
The report retains per-observation hashes, per-parameter estimates, deterministic grid-resolution
intervals, midpoint-baseline errors and held-out response errors. `warpOrientation` is explicitly
not calibrated because these scalar coupons do not identify it.

This is project-authored numerical evidence. Grid-resolution intervals are not statistical
confidence intervals, and successful recovery is not evidence of real-fabric physical accuracy.

## T-Shirt Motion Evidence

Every preset runs the existing fixed-avatar T-shirt reference solver. The report measures
convergence, maximum displacement, energy-decay proxy, directional strain, seam residual, opening
drift, body penetration, self-collision, triangle safety and finite positions. The resulting
simulation state reconstructs the render shell through the authoritative dense binding.

Bounded execution currently succeeds for all four presets, but D0 motion quality is rejected.
Opening drift is above the `0.08 m` provisional bound and unresolved self-collision remains. Those
failures are persisted; thresholds are not widened to manufacture acceptance.

## Evidence Tiers

- Descriptor/schema and deterministic fixture selection: executed D0 public-fixture evidence.
- Numerical calibration fixtures: executed, but not real-fabric measurement.
- Synthetic inverse calibration and unseen authored holdouts: executed, but not real-fabric
  measurement or learned inference.
- Fixed-avatar T-shirt CPU motion and dense reconstruction: executed.
- Learned material inference: not run.
- Private-user material estimation: not run.
- Production GPU motion, mobile performance and real-fabric calibration: not run.
