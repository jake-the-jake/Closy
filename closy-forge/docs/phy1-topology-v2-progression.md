# PHY1 Topology-v2 Progression

## Scope

This review unit introduces `closy.simulation_topology.v2` and
`closy.interior_constrained_triangulator.v2` only for a bounded physical experiment. Historical v1
PHY1 failure evidence is preserved. The accepted Closy D runtime remains exactly pinned to topology
v1 and exposes no v2 package, binding, derivative, or capability.

## What Executed

- A deterministic interior tessellator preserves authored boundary samples/order, panel UVs, seam,
  opening, grain and material semantics. It emits stable vertex/triangle provenance and remaps.
- Static audits enforce scale-aware double area, minimum angle, maximum aspect and edge length,
  manifoldness, unique faces, winding, finiteness, polygon containment, and no T-junctions.
- Explicit seam endpoint equivalence audits duplicate/conflicting/zero constraints, incompatible
  many-to-one mappings, easing, openings and high-valence junctions without tolerance inflation.
- Render topology and binding are rebuilt from v2 and stale v1 binding corruption is rejected.
- The qualified rotation-invariant temporal oracle executes on the exact frozen 11-state replay.
- Simulation and dense render vertices are independently checked against the same exact frozen
  solver collision primitives with cloth half-thickness deducted.
- The full report, profile, topology, seam, binding, invalidation, and final D0 matrix artifacts are
  regenerated twice with byte-identical hashes.

## Result

Static topology, seam, binding, determinism, performance, and temporal orientation pass. Qualified
temporal degeneracy, swept collapse, and true inversion counts are all zero, compared with
`198/191/15` in v1. This is not a PHY1 pass.

All 11 complete physical states fail. The aggregate witnesses are:

- maximum unresolved contacts: `867`;
- maximum residual depth: `0.0023990773806180504 m` against `0.000160000 m`;
- residual violations: `4143`;
- minimum simulation/render clearance: `-0.014360828541598742 m` /
  `-0.06446662127412164 m` against `+0.000005 m`;
- maximum seam crack/slip: `0.4175469103909202 m` / `0.4175469103909202 m`;
- edge stretch/compression extrema: `3.2505437360873835` / `0.32661302857743224`;
- area-ratio extrema: `0.024510115` / `86.922363144`;
- maximum support drift: `0.34943661366549605 m`;
- settle convergence: failed.

Coupled convergence is therefore not established. Integrated CCD is ineligible and was not run.
No stable/realistic cloth, production physical animation, solver-driven Phase 11, Z2, Alpha, GPU,
device, private-user, real-fabric, licensed-body, or human-review claim follows.

## Performance And Budgets

The bounded full source/CPU profile was observed once at `62.8124435 s` on an Intel Core i7-6700HQ,
Windows 10, CPython 3.11.4, one thread, under the `180 s` ceiling. Peak process memory was not
measured and is recorded as such. A superseded dense exact-GLB signed-distance trial exceeded 210
seconds and was stopped; it is excluded rather than reported as successful performance evidence.

One of three topology strategies and one of two seam models were consumed. The review unit stops at
the smallest truthful failure and does not append an unqualified solver rewrite.

## Final D0 Matrix

The required fixed-avatar T-shirt matrix is `partial`: 8 rows pass and 6 are not run. The first unmet
requirement is decoded front/rear raster ingestion and source identity for the exact integrated
selection. Existing raster experiments are not linked to that exact identity and are not used as
proxy evidence. C3, conventional fallback, candidate static Z1, MT1, deterministic rebuild, exact
hashes, and unsupported-claim controls remain independently recorded.
