# C3 D0 Binding and Collision Closeout

This document is the human-readable companion to
`reports/production_binding_c3.json` and `reports/self_collision_report.json`. The reports are the
machine-readable authority. This increment does **not** close Gate C3.

## Declared Profile

- Garment: project-authored fixed-avatar D0 T-shirt fixture.
- Runtime: deterministic Python 3.11 CPU reference implementation.
- Dense route: persisted barycentric simulation-to-render binding.
- Fallback route: independently reconstructed simulation-mesh fallback.
- Motion suite: eleven persisted solver-produced states.
- Performance evidence: non-canonical host CPU measurement only; never a mobile or frame-time
  claim.

## Corrected Metric Semantics

Dense and fallback meshes have different tessellation density. The v3 report therefore replaces
unweighted vertex-centroid parity with independently implemented area-weighted surface centroids,
normalised XYZ bounds, symmetric point-to-triangle sampled surface distance, semantic extrema,
opening landmarks, and seam-path landmarks. Tests include biased retessellation and symmetric
route corruption cases that expose the old metric's failure modes.

Seam tangential slip is now the paired-side relative gap motion projected onto the average rest
seam-path tangent. Shared whole-cloth motion is removed. Absolute midpoint travel is retained only
as a diagnostic and is not a gate metric.

## Authoritative Current Result

The rebuilt package reports:

- area-weighted dense/fallback centroid delta: `0.0 m`;
- maximum sampled surface distance: `0.000000033 m`;
- semantic landmark delta: `0.0 m`;
- maximum seam crack residual: `0.057059358 m` against `0.060 m`;
- maximum relative tangential slip: `0.016578367 m` against `0.045 m`;
- stitched-shell passing states: `0 / 11`;
- minimum stitched-shell/body clearance: `-0.099391794 m`;
- self-collision contacts: `271` before correction, `137` after correction;
- maximum residual collision depth: `0.002327721 m`;
- predeclared residual-depth budget: `0.000160000 m`.

The older prose value of 36 unresolved contacts is stale. The persisted recomputable v3 reports,
which currently record 137 unresolved contacts, are authoritative.

## Stitched Render Shell

Every state loads the persisted `render/stitched_shell.glb`, verifies it against the logical-shell
topology, and deforms its 81 vertices using the persisted source-vertex classes. The evaluator does
not call dense reconstruction. It recomputes frames, opening perimeters, topology/index stability,
seam welding, body clearance, and source stitch proof. Layer separation is explicitly not
applicable to this single-layer T-shirt.

The route remains failed because the deformed shell has substantial body penetration and the
existing ordered-correspondence stitch audit is not proven. These failures are recorded rather
than hidden by the now-correct dense/fallback metrics.

## Collision Scope

The collision pass has explicit adjacency/seam exclusions, deterministic broad and narrow phases,
bounded correction iterations, and post-solve contact recomputation. Bounded temporal subdivision
fixtures pass for fast crossing, thin layers, and opening boundaries; motion that exceeds the
declared bound fails closed. This proves the fixture detector only. CCD response is not integrated
into the reference motion solver, and production GPU collision remains false.

## Gate Decision

`gateC3Status` remains `partial`. The exact D0 profile cannot pass until all of the following are
true without widening the existing thresholds:

- real stitched-shell source correspondence is proven;
- stitched-shell body clearance passes over every persisted state;
- stitched-shell triangle/frame/opening checks all pass;
- self-collision reaches zero unresolved penetration, or remains within the predeclared physical
  depth budget;
- bounded CCD response is integrated where the profile claims motion support.

Broader C3 also remains blocked on provider/private-avatar tiers, production GPU/mobile evidence,
and broader garment/motion coverage.

## Exact-Commit Host Performance

`docs/evidence/C3_D0_CPU_BENCHMARK_628738e.json` was measured from implementation commit
`628738e5e8bc2da89be2ae1c349d9a2a220d8839` on Windows, Python 3.11, using three warmups and
twenty binding-route samples. Solver/collision routes use five samples; stitched-shell and C3
validator routes use three because they are substantially slower.

- dense route, one state: median `16.780950 ms`, p95 `20.824400 ms`;
- dense route, eleven states: median `205.413100 ms`, p95 `238.309200 ms`;
- fallback route, eleven states: median `0.931900 ms`, p95 `1.147700 ms`;
- solver, one state: median `5976.551200 ms`, p95 `6245.301800 ms`;
- self-collision, one state: median `6382.796900 ms`, p95 `6477.767300 ms`;
- stitched-shell suite: median `11189.541800 ms`, p95 `11189.541800 ms`;
- C3 validator: median `52542.102900 ms`, p95 `52542.102900 ms`.

Peak memory is Python-allocation-only and is recorded per route in the JSON evidence. In
particular, the roughly `205 ms` dense suite is offline CPU evidence and is not described as
real-time mobile performance.
