# Active Blueprint Resume

This file is a recoverable checkpoint for the continuous Closy master-blueprint work. It records current evidence without citing future CI from the commit that contains this update.

## Current State

- Active blueprint checkpoint: `PHASE-6-D0-BINDING-C3-SELF-COLLISION-EVIDENCE`
- Exact subtask: implement the scoped D0 fixed-avatar T-shirt production binding contract, C3 evidence report and deterministic reference self-collision backend on the Phase 6 branch.
- Current branch: `codex/closy-forge-phase-6-binding`
- Parent branch / PR target: `codex/closy-forge-phase-5-provider`
- Phase 6 branch point: `97bf23ccff13e806132b732534d131d80b146467`
- Verified Phase 5 provider PR evidence: PR #6 passed GitHub Actions run `32848455025`; Ubuntu job `97803514100` and Windows job `97803513678` ran 113 format-checked files, mypy over 90 source files, 210 tests, fresh schemas, byte-identical package trees and digest `12b3f768a1916c593574514bb5f5d25a9456415acfddb5e57aadb32381a9bc95` with only `self_collision_not_run`.
- Current package evidence: two local builds `.tmp\phase6_binding_A_20260825.closygarment` and `.tmp\phase6_binding_B_20260825.closygarment` are byte-identical with 93 physical files each, 89 manifest-inventoried files, canonical digest `e02b5b19450d72f5e74a30d117cbcd7ab45de1451823b22bfa834f3a548a0711`, validation status `passed`, and only warning `self_collision_unresolved_contacts`.
- Production binding contract evidence: `binding/production_binding_contract.json` records stable render vertex IDs, source/destination hashes, triangle/barycentric weights, logical-to-render split mappings and opening safeguards for the D0 T-shirt profile.
- Production binding C3 evidence: `reports/production_binding_c3.json` uses `stageVersion=closy.production_binding_c3.d0_tshirt.v1`, `profile=d0_fixed_avatar_tshirt_dense_fallback`, `gateC3Status=complete_for_d0_fixed_avatar_tshirt_profile`, `motionStateCount=11`, persisted validation `pass`, max reconstruction error `0.004996001`, max seam crack `0.047774031`, dense/fallback parity error `0.0`, and explicitly keeps global Phase 6, clean proposal and canonical geometry false.
- Self-collision evidence: `reports/self_collision_report.json` uses `stageVersion=closy.self_collision.reference_d0.vertex_triangle_v1`, runs broad phase, narrow phase, correction, brute-force oracle and adversarial fixture checks, records 3598 candidate pairs, 36 contacts after correction, 36 unresolved D0 reference contacts, and `unsupported_high_velocity_tunnelling`.
- Current validator warning semantics: the old `self_collision_not_run` warning is removed from new packages; unresolved D0 reference contacts are reported as `self_collision_unresolved_contacts`.
- Known unrelated local work outside this Forge slice remains unstaged and must be preserved: `metro.config.js`, app avatar files under `src/features/avatar-*`, and untracked `closy-forge/.tmp/`.

## Checks Completed At Current Local Checkpoint

- `.\.venv\Scripts\ruff.exe format --check .` passed over 117 files.
- `.\.venv\Scripts\ruff.exe check .` passed.
- `.\.venv\Scripts\mypy.exe src` passed over 92 source files.
- `.\.venv\Scripts\python.exe -m closy_forge schemas check --schema-dir schemas\v1 --json` returned `{"issues":[],"status":"fresh"}`.
- Focused C3/self-collision/golden/schema tests passed: 12 tests covering production binding contract/C3 evidence, C3 tampering, self-collision fixtures, self-collision report recomputation, reference solver diagnostics, golden summary and schema freshness.
- Full `.\.venv\Scripts\python.exe -m pytest -q` exited 0; collect-only counted 217 Forge tests across 23 test files.
- Deterministic package diff passed for `.tmp\phase6_binding_A_20260825.closygarment` and `.tmp\phase6_binding_B_20260825.closygarment`: status `identical`, 93 files on each side, digest `e02b5b19450d72f5e74a30d117cbcd7ab45de1451823b22bfa834f3a548a0711`.
- Independent validate/report passed: validation counts `info=0`, `warning=1`, `error=0`, `fatal=0`; only issue code `self_collision_unresolved_contacts`; CLI report includes `Production binding C3: status=d0_c3_profile_pass_clean_rejected` and `Self-collision: status=d0_reference_self_collision_run_with_unresolved_contacts`.

## Current Truth And Limits

- Phase 6 has a scoped D0 C3 profile pass for the fixed-avatar T-shirt dense/fallback binding path.
- This is not global Phase 6 completion, not clean/canonical geometry acceptance, and not production mobile GPU proof.
- The production binding contract covers stable render vertex IDs, source/destination hashes, triangle/barycentric weights, logical-to-render split mapping and opening safeguards for the current D0 fixture.
- The self-collision backend is deterministic D0 reference evidence only; it retains unresolved contacts and explicitly does not support high-velocity tunnelling.
- Provider output remains proposal-only. No AI/open-model provider execution, external provider execution, source/provider visual-fidelity acceptance or canonical clean mesh promotion is included in this branch.

## Next Exact Command

```powershell
git status --short --branch
```

## Next Safe Action

Commit only the Forge Phase 6 files on `codex/closy-forge-phase-6-binding`, leaving unrelated avatar/metro work untouched. Push the branch, create a stacked draft PR targeting `codex/closy-forge-phase-5-provider`, wait for Ubuntu/Windows Forge CI, inspect both job logs, update the PR body with exact run/job evidence, and then create a remote evidence-sync commit if the implementation run is green.
