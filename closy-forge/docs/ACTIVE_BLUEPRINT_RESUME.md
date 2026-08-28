# Active Blueprint Resume

This checkpoint is subordinate to `current_blueprint_status.json`,
`blueprint_coverage.json`, `pr_stack_manifest.json`, and the committed execution evidence.
Green CI proves only the exact checks that ran and never promotes a global blueprint phase.

## Active Stack

- Repository: `jake-the-jake/Closy`.
- Integrity parent: draft PR #24, branch
  `codex/closy-forge-evidence-security-integrity-v2`, head
  `5d080caad354bcecff94a7eadf16d080d68a606c`; exact-head Forge run `33183367784`
  passed all required jobs.
- C3/PHY1 sibling: draft PR #25, branch
  `codex/closy-forge-c3-physical-convergence-v2`, head
  `f9f1ff86089f6b43157431bdd3ccdc83cbc8b974`; based directly on PR #24. Exact-head
  run `33203903630` passed static and family lanes but failed both cumulative integration shards
  because new collision diagnostics changed established package bytes.
- Independent Phase 9 sibling: draft PR #26, branch
  `codex/closy-forge-phase-9-raster-trained-synthetic-d0`, head
  `ba73b310a8609de4eb4f0ed2284c6d2d9a6fab53`; based directly on PR #24. Exact-head
  run `33201911956` passed all 26 jobs.
- Phase 10 sibling and reconciliation parent: draft PR #27, branch
  `codex/closy-forge-phase-10-zeroone-static-integration-v2`, head
  `2a4fcd8146d95d2fab9a3d39751ffdafd5196387`; based directly on PR #24. Exact-head
  run `33203908161` passed all 26 jobs.
- Reconciliation candidate: branch
  `codex/closy-forge-phase11-prerequisite-reconciliation-v2`, based on exact PR #27 head.
  It replays only the eight reviewed PR #25 commits with `-x`, then restores legacy reference
  package payload compatibility and updates only the intentionally changed T-shirt C3 golden.
  Phase 9 remains independent.
- No PR was merged, retargeted, or force-pushed. Published parent branches remain immutable.

## Canonical Status

- Requirement rows: 21 complete, 59 partial, 8 not started, 13 discovery pending,
  101 total.
- Phase 0 is complete. Phases 1 through 14 remain partial.
- C1 and C2 retain scoped passes.
- `C3-Binding-D0` passes only for the fixed-avatar, project-authored T-shirt D0 profile.
- `PHY1-SingleLayer-D0` fails its exact physical profile.
- Refreshed paired candidate Z1 fails its all-family scope: all nine families ran, six passed,
  and three were rejected fail-closed.
- Z2 through Z8 and P1 remain not run or discovery pending.
- Research Prototype is partial. Alpha, Beta, and Production are not started.

## C3 Binding And PHY1 Truth

- C3 source evidence is commit `1a500b1720edeae4a3f28b88a31f7cd14125854b` under profile
  `closy.c3_binding.d0_tshirt.v1` with profile hash
  `c80e6123c360ab1633e4aa821cdbefbac3553807ee330d28867ac870e0a625a1`.
- All 11 binding states pass. There are 1,248 persisted binding records and 1,248 stable
  render-vertex IDs. Maximum reconstruction error is `0`, and maximum independent
  dense/fallback sampled-surface distance is `0.000000038 m`.
- PHY1 self-collision falls from 33 contacts to 9 unresolved contacts. Residual depth is
  `0.001878992 m` against a `0.000160000 m` budget, with four violations above budget.
- Contact count is monotonic non-increasing; maximum depth is not. Rest-referenced
  inverted-or-degenerate triangles fall from 70 to 68, with zero newly introduced triangles.
- Maximum seam crack is `0.109609688 m`; minimum stitched-shell body clearance is
  `-0.009084014 m`; 0 of 11 physical states pass.
- Bounded CCD fixtures pass, but no canonical performance benchmark, GPU run, mobile run,
  private-user run, or human review ran.
- C3 permits a mechanical/reference Phase 11 slice only after refreshed paired scoped Z1 passes.
  PHY1 remains separately required for solver-driven physical-quality claims.

## Refreshed Phase 10 And Z1 Truth

- ZeroOne source is the unmerged candidate PR #2 head
  `13a844d240f4bbb2cafde105c4a0bdca8d89a06b`.
- The trusted Windows Release executable SHA-256 is
  `59bb051455ae2878a30edd353bdb451271107bb5df3e3570b89b955379cf2065`.
- The exact durable ZeroOne workflow run is `33187775880`; the paired Closy execution is local
  candidate evidence, not a durable paired workflow artifact or current-master qualification.
- T-shirt, sleeveless top, simple skirt, simple trousers, simple dress, and layered asymmetric
  pass static cook, cache, deletion/rebuild, namespace validation, authority preservation,
  fallback preservation, and independent derivative inspection.
- Long-sleeved top, button shirt, and jacket/outerwear are rejected during cook with
  `E_SURFACE_BUILD:invalid_surface_topology:surface triangle is degenerate`.
- No failed family silently receives a derivative. Every conventional fallback remains present.
- Therefore candidate all-family Z1 is failed, global Z1 and Phase 10 remain partial, and Phase 11
  does not branch from this checkpoint.

## Independent Phase 9 Truth

- Phase 9 executed an actual deterministic CPU optimisation on 384 raster-derived captures from
  96 identity-disjoint project-authored programs across eight families.
- Held-out top-1 is `53/64` (`0.828125`) and top-3 is `1.0`; the deterministic nearest-centroid
  baseline top-1 is `0.90625`, so no learned-superiority claim is made.
- Four of eight learned downstream builders are accepted; all eight downstream package paths
  validate through deterministic fallback where required.
- E1 is partial, E2 was not run, and global Phase 9 remains partial.
- PR #26 remains an independent sibling and does not block Phase 11 or static Phase 12 preparation.

## Phase 11 Decision

- No compiled ZeroOne dynamic request, report, command, profile, derivative namespace, or Z2
  evidence was created.
- `C3-Binding-D0` is satisfied, but refreshed paired scoped Z1 is not. The mechanical/reference
  Phase 11 prerequisite set is therefore incomplete.
- `PHY1-SingleLayer-D0` also fails, so solver-driven physical-quality claims remain prohibited.
- The next eligible implementation lane is one bounded, source-only Phase 12 static-runtime
  preparation sibling, plus repair of the three canonical surfaces required to rerun paired Z1.

## Preserved State

- The primary Closy checkout and all earlier published worktrees remain untouched by this
  reconciliation.
- Task-owned evidence, generated review images, recovery state, and exact executable records are
  retained. No unrelated user edits or untracked files were deleted.
- Native ZeroOne binaries are not committed into Closy.

## Exact Next Action

Repair the three rejected conventional fallback surfaces without changing canonical pattern,
seam, opening, layer, or material authority. The preferred bounded direction is a seam-aware
render-side weld/remap or a new versioned nondegenerate surface profile, followed by regenerated
bindings, exact package validation, rebuilt ZeroOne, and a fresh paired all-family Z1 run.

Do not begin Phase 11, claim Z2, claim PHY1, merge, retarget, force-push, widen thresholds,
filter contacts, or silently skip failed families.
