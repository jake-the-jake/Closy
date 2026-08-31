# PHY1 Seam-Support v3 Closeout

## Scope and frozen identity

Review unit D is a bounded, solver-active neutral experiment over the exact finite Unit C candidate.
It does not replace or combine the Unit C visual verdict with historical PR #39 physical evidence.

- Parent head: `7922e9b6ece8fca2c3b7dec13299a39de102cbc4`
- Candidate: `candidate.d0_exact_fitted_topology_v2.060e8d4aaaa7e82eddb75880`
- Physical candidate: `physical.candidate.phy1_seam_support_v3.1152728eaf2588b4f674339f`
- Candidate package digest: `aa3b6345d6fab56a59d9b0acbd05a8526ffdb473e8174f90f88fd255d8514ca2`
- Pattern hash: `e476864cbd1434831e66008f151585f3feebbd7299b209bdb8accc308e6fd207`
- Seam-constraint hash: `3026459bcde9762070862644e1740cfb57d6241406aae9927010a8513e617c6a`
- Simulation-topology hash: `c6e80ed085302172d06296d276404d1441b3463e166b8058ab999b7bd62016ee`
- Threshold profile: `closy.phy1.seam_support_neutral.v3`

The pattern, seam-constraint and simulation-topology hashes are byte-identical to the PR #39 budget
identity, so its bounded budget carries forward. v3 consumes the second and final seam model, consumes
no new topology strategy, and leaves two topology strategies reserved.

## Executed contract

The preregistered implementation provides:

- six non-vacuous authored junction classes with deterministic rank-aware `n-1` constraints;
- zero-gap stitch constraints whose ease is encoded by normalised arclength correspondence;
- independent crack, tangential-slip, arclength/ease and Euclidean-gap metrics;
- eight pose-driven shoulder supports with an explicit ramp and release before the scored tail;
- body and self-collision projections during solve iterations;
- independent triangle/body and triangle/triangle collision oracles;
- bounded CPU XPBD solve-to-convergence with persisted support, energy and stop-reason records;
- 49 non-static trajectory frames, deterministic repeat and delete/rebuild evidence;
- 11 analytic/corruption controls covering junction, seam, support, collision, identity and trajectory
  failure modes.

The lock was committed before analytic execution and before the candidate run. The analytic preflight
and all 11 corruption controls passed before the neutral candidate was executed.

## Reporting repair

The original validator exposed a reporting-only precision mismatch: in-memory Python float hashes were
compared directly with persisted GLB `float32` hashes. An independent `float32` microfixture proved the
cause. The evaluator was versioned to
`closy.phy1.seam_support_v3.neutral_preflight.v2_persisted_rescore`, and the original 49 persisted
trajectory frames were rescored. No solver input, equation, support, collision cadence, threshold or
trajectory byte changed, and the solver was not rerun for the repair.

## Result

The persisted outcome is `A_neutral_preflight_failed_v3`: 11 of 28 checks pass and 17 fail. Important
measured failures include:

| Predicate | Frozen limit | Observed |
|---|---:|---:|
| unresolved self contacts | `0` | `242` |
| maximum residual depth | `0.00016 m` | `0.0024 m` |
| simulation clearance | `>= 0.000005 m` | `0.0 m` |
| dense render clearance | `>= 0.000005 m` | `-0.050591166989 m` |
| seam crack | `<= 0.002 m` | `0.041513220488 m` |
| tangential slip | `<= 0.005 m` | `0.145067036152 m` |
| active support residual | `<= 0.002 m` | `0.2198415495 m` |
| terminal velocity | `<= 0.02 m/s` | `1.7125970577601999 m/s` |
| terminal kinetic energy | `<= 0.001 J` | `0.008777274630228434 J` |
| maximum edge stretch | `<= 1.35` | `23.224366506480806` |
| minimum edge compression | `>= 0.75` | `0.2284016813534197` |
| shear | `<= 0.35` | `13.002133621574329` |
| area ratio | `[0.65, 1.5]` | `[0.083057001, 26.129675575]` |
| runtime ceiling | `<= 180 s` | `263.656 s` primary |

The complete evidence inventory is under `docs/evidence/phy1_seam_support_v3`. Its inventory digest is
`280df4684724d2dae73eb20a09008aec824c2c6476ed21325c754c9c05ef1b4c`; the neutral evidence hash is
`24a599b7d6def63417347595c9a09afec3fa2ce7c03e65e0d111b40256f3c697`; and the outcome hash is
`4271468de3c4b0f29704e46379c082b8d49bac9adf38f4c70a3d16428d61bbd3`.

## Stop-rule and capability truth

The failed neutral gate stops this physical lane. Full 11-state PHY1, CCD and solver-driven Z2 were not
run. Runtime v1 remains selected and topology v2 remains opt-in. The final D0 matrix is 9 pass, 3 fail
and 3 not-run; the first literal Research Prototype predicate still unmet is `D0-RP-07`. Exact C3
strict acceptance (`D0-RP-08`) and neutral physical acceptance (`D0-RP-15`) also fail.

This evidence does not support human review, private-user, real-photo, real-fabric, GPU, mobile,
production animation or product-readiness claims.

## Next dependency-ready milestone

Start a new branch only after this draft PR has exact-head CI authority. The next physical experiment
must use a new seam-model budget authority because both seam models are consumed. Preserve the two
remaining topology strategies until an independently preregistered seam/support model passes analytic
controls and isolates topology as the blocker. Do not run CCD or Z2 before a neutral candidate passes.
