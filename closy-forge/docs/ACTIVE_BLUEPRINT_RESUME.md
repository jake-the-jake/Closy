# Active Blueprint Resume

This file is a recoverable checkpoint for the continuous Closy master-blueprint work. It records current evidence without trying to cite future CI from the commit that contains this update.

## Current State

- Active blueprint checkpoint: `PHASE-5-PROVIDER-CONTRACT-BAKEOFF-LOCAL-EVIDENCE`
- Exact subtask: publish the scoped Phase 5 garment/avatar-only provider contract slice, then open a stacked draft PR targeting the verified BP46 PR #5 head.
- Current branch: `codex/closy-forge-phase-5-provider`
- Parent branch / PR target: `codex/closy-forge-foundation-proof-closeout`
- Phase 5 branch point: `756b0211d9c3ba7aa3b63b0f9c1896d7da143c9a`
- Latest Phase 5 implementation commit SHA: `12322a1eb23e5f0cd8361ecc01be419bbc175364`
- Latest Phase 5 implementation commit subject: `Add Phase 5 provider contract bakeoff`
- Foundation proof draft PR #5: `https://github.com/jake-the-jake/Closy/pull/5`, draft/open, stacked on `codex/closy-forge-phase-4-texture`.
- Verified PR #5 freeze evidence: GitHub Actions run `32835151202` passed at `756b0211d9c3ba7aa3b63b0f9c1896d7da143c9a`; Ubuntu job `97762247917` and Windows job `97762247732` each ran 112 format-checked files, mypy over 89 source files, 199 tests, fresh schemas, byte-identical 89-file package trees, package digest `d22b3d4392ce599ceeff6714eec39bf3d6c543cbeb7ff1a6953a363672b80cb5`, and validation/report with only formal warning `self_collision_not_run`.
- Phase 5 local package evidence after `12322a1`: two temp package builds `.tmp\phase5_provider_A.closygarment` and `.tmp\phase5_provider_B.closygarment` are byte-identical, 90 physical files each, digest `12b3f768a1916c593574514bb5f5d25a9456415acfddb5e57aadb32381a9bc95`, validate status `passed`, and only formal warning `self_collision_not_run`.
- Current provider registry evidence: `proposals/provider_registry.json` uses `stageVersion=closy.geometry_provider_registry.phase5_contract_v2`, `contractVersion=closy.provider_contract.garment_avatar_only.v1`, declares three providers, selects `closy.manual_local_glb_import.v1`, declares `closy.local_open_model_geometry_adapter.v1`, keeps local open-model execution false, denies network/socket/model-hub access, and preserves provider output as proposal-only non-canonical evidence.
- Current provider bake-off evidence: `reports/provider_bakeoff.json` uses `stageVersion=closy.provider_bakeoff.phase5_contract_v1`, `status=completed_d0_contract_only_clean_rejected`, `providerCount=3`, `executedProviderCount=1`, `notRunProviderCount=2`, `canonicalAcceptedProviderCount=0`, best provider `closy.manual_local_glb_import.v1`, and local open-model status `not_run_missing_runtime_or_weights`.
- Clean/canonical acceptance remains rejected. The provider slice adds contract, registry, manual fixture and bake-off evidence only; it does not execute an AI/open-model provider, accept external provider output, perform source/provider visual fidelity, run private-user processing, or promote any provider mesh to canonical truth.
- Known unrelated local work outside this Forge slice remains unstaged and must be preserved: `metro.config.js`, app avatar files under `src/features/avatar-*`, and untracked `closy-forge/.tmp/`.

## Checks Completed At Current Local Checkpoint

- `.\.venv\Scripts\ruff.exe format --check .` passed over 113 files.
- `.\.venv\Scripts\ruff.exe check .` passed.
- `.\.venv\Scripts\mypy.exe src` passed over 90 source files.
- `.\.venv\Scripts\python.exe -m closy_forge schemas check --schema-dir schemas\v1 --json` returned `{"issues":[],"status":"fresh"}`.
- Focused provider/golden/schema tests passed, including provider registry/bake-off unit coverage, provider contract lifecycle/limit safe-failure coverage, bake-off corruption coverage, CLI report JSON/text coverage, schema freshness and the golden demo summary.
- Full `.\.venv\Scripts\python.exe -m pytest -q` exited 0; collect-only counted 210 Forge tests across 21 test files.
- Deterministic package diff passed: `.tmp\phase5_provider_A.closygarment` and `.tmp\phase5_provider_B.closygarment` are identical with 90 files each and digest `12b3f768a1916c593574514bb5f5d25a9456415acfddb5e57aadb32381a9bc95`.
- Independent validate/report passed: validation counts `info=0`, `warning=1`, `error=0`, `fatal=0`; only issue code `self_collision_not_run`; CLI report includes `Provider bake-off: status=completed_d0_contract_only_clean_rejected, executed=1/3, best=closy.manual_local_glb_import.v1, canonical accepted=0`.

## Current Truth And Limits

- Phase 5 is advanced as a local D0 provider-contract slice, not completed as full model-provider execution.
- Null/manual providers are exercised for deterministic CI and fail-closed operation; manual fixture import is project-authored non-model evidence.
- The local open-model adapter is only a declared boundary until authorised runtime, weights, hardware, license/SBOM evidence and isolated execution exist.
- External providers remain unconfigured and must not be called or uploaded to without explicit future authority.
- Provider outputs remain non-canonical. Pattern/seam/simulation truth remains canonical, and clean acceptance still rejects clean/canonical promotion.
- BP46 topology/opening proof remains frozen on PR #5; production stitched-shell sim-to-render binding, crack/sliding proof and C3 runtime evidence belong on the later Phase 6 branch.

## Next Exact Command

```powershell
git status --short --branch
```

## Next Safe Action

Push `codex/closy-forge-phase-5-provider`, create a draft PR targeting `codex/closy-forge-foundation-proof-closeout`, wait for Ubuntu/Windows Forge CI at commit `12322a1eb23e5f0cd8361ecc01be419bbc175364`, inspect both job logs, update the PR body with exact run/job evidence, and then create a remote evidence-sync commit if the implementation run is green.
