# Phase 7 solver formulation audit

This program is **solver-space parameter recovery**, not physical material calibration.

The repository reference backend is XPBD-like: distance constraints use compliance scaled by the
time step, while support and several material controls remain bounded gains. The public descriptor
contains SI-labelled nominal fields and a second `solverCoefficients` object, but the mapping is not
dimensionally derived from specimen geometry, constitutive stress/strain, thickness, or Poisson
coupling. Surface density is used as mass-per-area, gravity is in m/s2, time is seconds, and collision
clearance is metres; stretch, shear, bend, damping, friction, and restitution semantics are mixed.

The Phase 7 forward source therefore uses normalized `[0,1]` solver-space fields. It executes a
higher-resolution discretized strip trajectory. The production comparison uses separately coded,
lower-resolution state updates and different node count, time step, iteration count, contact cap,
and constraint gains. Both remain correlated project-authored numerical models, not independent
physics oracles. Compression/thickness is unsupported and remains `not_run` in the denominator.

Unit AE remains historical analytic round-trip evidence and is not reused as solver evidence.
Real-coupon ingestion is schema-only until actual measured, licensed observations are supplied.
