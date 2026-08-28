# Active Blueprint Resume

This checkpoint is subordinate to the machine-readable authorities
`current_blueprint_status.json`, `blueprint_coverage.json`, and
`pr_stack_manifest.json`. Green CI proves only the checks that ran; it does not promote a
global blueprint phase.

## Active Stack

- Repository: `jake-the-jake/Closy`.
- Audited cumulative parent: draft PR #19, branch
  `codex/closy-forge-phases-10-14-runnable-foundations`, SHA
  `e83e1e897c9539d246926f8148c5a9ac347982d1`.
- Integrity: draft PR #20, branch
  `codex/closy-forge-evidence-topology-physics-integrity`, head
  `3f02a9fde0cbbb52526bd3dd11e6d0bf0f665148`.
- C3 closeout: draft PR #21, branch `codex/closy-forge-c3-collision-closeout`, head
  `c5db68d4054141e3bd82aea848c292ec78179fcd`.
- Learned Phase 9: draft PR #22, branch
  `codex/closy-forge-phase-9-trained-synthetic-d0`, head
  `988b242cc441006257d969d9980373213330743c`.
- Real static Phase 10: draft PR #23, branch
  `codex/closy-forge-phase-10-zeroone-static-integration`; clean execution anchor
  `13c3d281843750c7bcd9db50e309ed129066e9fe` and evidence commit
  `c1a97f1b23a7a2fb3eda666e03fc66c369916031`; inherited verification/evaluation
  head `7016a53f89d6085678652c30df6346e67db9da4c`.
- Every continuation branch is stacked on its preceding draft PR with an exact direct-parent
  merge base and zero behind commits. No PR was merged, retargeted, or force-pushed.

## Canonical Status

- Requirement rows before this progression: 20 complete, 57 partial, 8 not started,
  16 discovery pending, 101 total.
- Requirement rows after reconciliation: 22 complete, 58 partial, 8 not started,
  13 discovery pending, 101 total.
- Phase 0 is complete. Phases 1 through 14 remain partial.
- C1 and C2 have scoped passing evidence. C3 remains partial. Z1 is complete only for the exact
  tested Windows MSVC Release D0 CPU/static profile. Z2 and P1 remain discovery pending.
- The research prototype is partial. Alpha, Beta, and Production are not started.
- Phase 8 family bundles remain deterministic D0 fixture artifact bundles, not globally complete
  garment families.
- Phase 10 now has real, pinned ZeroOne CPU/static execution for two project-authored D0 fixtures.
  Phases 11 through 14 remain versioned contract-fixture foundations.

## Verification Scaling

- Unit and corruption tests are assigned exactly once across four deterministic shards on Ubuntu
  Python 3.11, Windows Python 3.11, and Ubuntu Python 3.12. Static format, lint, typing, and schema
  checks run in a separate fast lane.
- Integration and golden tests are assigned exactly once across two cumulative shards; the
  non-canonical binding benchmark runs on shard 0. The eight family rebuilds remain split across
  three stable family groups and all three supported runtime combinations.
- The former serial local unit/corruption run exceeded 3,838 CPU seconds and the former hosted
  cumulative lane hit its 35-minute limit. The bounded local integration shard 0 now passes 19
  tests in 1,446.01 seconds without increasing a timeout.

## C3 Truth And Phase 11 Gate

- Independent area-centroid and semantic-landmark error are `0`; sampled-surface maximum error is
  `0.000000033 m`.
- Relative seam slip is `0.016578367 m` and seam crack is `0.057059358 m`, both within their
  unchanged scoped thresholds.
- The persisted stitched render shell passes `0/11` states. Minimum signed body clearance is
  `-0.099391794 m`.
- Self-collision falls from `271` contacts to `137` unresolved contacts, with
  `0.002327721 m` residual depth against the declared `0.000160000 m` budget.
- Bounded swept/CCD fixtures pass, but CCD response is not integrated into the reference motion
  solver.
- C3 therefore does not pass. Phase 11 must not begin even though the independent static Z1 gate
  passes.

## Learned Phase 9 Evidence

- The v2 project-authored synthetic D0 dataset contains 96 identity-disjoint garment programs and
  384 observations. Held-out evaluation contains 64 observations.
- Training loss decreases from `2.346648555557` to `0.088242930902`.
- Held-out top-1 and top-3 family accuracy are `64/64`; grammar and seam validity are `64/64`.
- Mean absolute errors are `0.019518082` length scale, `0.021652209` width scale, and
  `0.267459873` normalized ease. OOD family accuracy is `30/32` (`0.9375`).
- The deterministic baseline is also `64/64`; no learned-superiority claim is made.
- Model hash is `2662e6a2e64fdfca6add84a1648da421652b6ef4249217078b5ad05e34a925ea` and
  weights hash is `59e7351a6b11a5381edfa31806727006c47c1a4c0ec3e4f6ba8508babd8a8e4c`.
- Training wall/CPU time is approximately `48.508 s`/`48.406 s`, peak memory is
  `44,036,096` bytes, and inference median/p95 is `0.3777 ms`/`0.5066 ms`.
- Global Phase 9 remains partial: evidence is synthetic, corrections are simulated, and no
  authorised real/public/private or human-review generalisation exists.

## ZeroOne Static Evidence

- ZeroOne source: `jake-the-jake/ZeroOne` at
  `c6388cbbf53ba8a47831ec25e83808e1edf32194`, draft PR #1.
- Executable: standalone Windows MSVC 19.36 Release, CPU-only and headless; it requires no GPU or
  window. SHA-256:
  `7629cb8d6953887636f1863d23f17e2e79002af79eedbacb3d3e99bba830990e`.
- Request/report profiles are `closy.zeroone.static-request.v1`,
  `zeroone.closy.static-report.v1`, and `closy-static-d0-cpu-v1`.
- T-shirt canonical digest is
  `2a97db3332ffce56f44c5ed7ff4bd5eb037c67219f3bcdc66e0131036f6c15d1`; derivative digest is
  `8b89b204ef7407c28ce709041809a621b69c3256f198c738ff1ff5eaa8d23461`.
- Layered-asymmetric canonical digest is
  `b8d211d347b1d74f6ff14a89ff81b150e8994a94fa07769081a1e3fedcc0faff`; derivative digest is
  `0cd8e9ebd6a92ebf9295db87aa10e95e2a9f6f594119694e71e3209bbe36e834`.
- Clean miss, cache hit, and second clean miss outputs agree. Canonical authority and conventional
  fallback hashes are unchanged. The optional namespaces validate. Deleting and rebuilding the
  T-shirt derivative reproduces the same hash.
- Final evidence records clean Closy and ZeroOne trees, `338,336,495,100` wall nanoseconds and
  `306,593,750,000` CPU nanoseconds. This proves scoped Z1, not global Phase 10 completion.

## Preserved Local State

The primary Closy checkout remains untouched with unrelated edits in `metro.config.js`,
`src/features/avatar-export/components/avatar-preview-dev-screen.tsx`,
`src/features/avatar-viewport/avatar-viewport-live.tsx`,
`src/features/avatar-viewport/live-viewport-debug-types.ts`,
`src/features/avatar-viewport/three.ts`, and untracked `closy-forge/.tmp/`.

Task worktrees also retain line-ending-only schema status and task-owned `.tmp/` directories.
Recovery stashes are intentionally retained and must not be dropped until the stack is accepted.

## Exact Next Command

The next implementation must continue C3 rather than Phase 11:

```powershell
cd E:\apps\Closy-c3\closy-forge
$env:PYTHONPATH = (Resolve-Path src).Path
& E:\apps\Closy-integrity\closy-forge\.venv\Scripts\python.exe -m pytest tests\unit\test_production_binding_c3.py tests\unit\test_production_self_collision.py -q
```

Do not merge, retarget, force-push, write to `main`/`master`, widen thresholds, filter unresolved
contacts, or promote Phase 11 while C3 remains partial.
