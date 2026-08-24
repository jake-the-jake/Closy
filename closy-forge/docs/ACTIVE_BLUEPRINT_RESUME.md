# Active Blueprint Resume

This file is a recoverable checkpoint for the continuous Closy master-blueprint work. It records evidence ancestry and next actions without trying to cite its own future commit SHA.

## Current State

- Active blueprint checkpoint: `BP-51-MULTIVIEW-CAPTURE-FUSION`
- Exact subtask: BP51 implementation is committed locally; record evidence, push, inspect remote CI, then resume at BP52 image-conditioned fitting only after green Ubuntu/Windows proof.
- Current branch: `codex/closy-forge-phase-2-capture`
- Parent branch: `codex/closy-forge-phase-0`
- Latest implementation commit SHA: `34023a0`
- Latest implementation commit subject: `Add BP51 multiview capture fusion`
- Record based on SHA: `34023a0`
- Draft PR: `https://github.com/jake-the-jake/Closy/pull/2`
- Parent draft PR: `https://github.com/jake-the-jake/Closy/pull/1`
- Last remote green evidence: GitHub Actions run `32711477463`; Ubuntu job `97383606003` and Windows job `97383605780` passed at commit `8dd32fe17647035bae2542171e56fe92bc74b047`.
- Last remote matrix details: Ubuntu job ran 4m55s and Windows job ran 9m24s; each ran 111 format-checked files, 88 mypy source files, 182 tests, fresh schemas, identical 83-file package trees, digest `8be718fdbf929a0f5112526fd4ae67d4f056ac3605d8e9ffd0593cee1b99708c`, and validation with only `self_collision_not_run`. Supabase Preview was skipped as expected for this Forge-only branch.
- Latest local BP51 evidence after `34023a0`: `ruff format --check .` reported 112 files already formatted; `ruff check .` passed; `mypy src` passed over 89 source files; schema check reported `{"issues":[],"status":"fresh"}`; focused BP51/golden/integration tests passed; full `pytest -q` passed 184 collected tests; two temp package builds were byte-identical with digest `8b9c00555f2ad904154640c77399e167ecb6da929d0c707a677a6d49f3c7c94a`, 85 package files, validation status `passed` and one formal warning.
- Formal package warning budget: exactly one package validator warning, `self_collision_not_run`.
- Clean acceptance report state: 13 checks with 9 pass, 1 fail, 2 warnings and 1 not-run; clean/canonical acceptance remains rejected.
- Current in-progress uncommitted work, if this file is read before the next commit: BP51 ledger/coverage/resume evidence update for implementation commit `34023a0`.
- Known unrelated local work outside this Forge slice remains unstaged and must be preserved: app avatar files, `metro.config.js`, and untracked `closy-forge/.tmp/`.

## Current BP-46/BP-47/BP-48/BP-49/BP-50/BP-51 Truth

- BP-46 still has `meshStitchOrWeldExecutionRun=true` backed by `stitch/logical_stitched_analysis_shell.json`, `render/stitched_shell.glb` and `reports/geometry_stitched_shell.json`.
- BP-46 still has `meshStitchOrWeldProven=false`, `acceptedForCleanProposal=false` and `acceptedForCanonical=false`.
- BP-47 adds deterministic SVG inspection artifacts and separated evidence tiers, but does not provide decoded raster visual fidelity, source/provider appearance comparison or signed human review.
- BP-48 adds persisted fallback GLB `NORMAL` and `VEC4` `TANGENT` accessors plus `reports/render_frame_pose_suite.json`.
- BP-48 validates four deterministic pose snapshots within the `1e-6` binding tolerance; after deterministic quantization the observed max pose binding error is `1e-09`.
- BP-48 records `renderTangentsPersistedAvailable=true`, `poseSuiteBindingEvidenceAvailable=true` and `acceptedForRuntimeFramePreview=true`.
- BP-48 keeps `acceptedForCleanProposal=false` and does not complete Phase 6 or Gate C3.
- BP-49 implements only `synthetic_fixture_raster_v1` for project-authored local PNG/JPEG fixtures. It rejects user imagery, provider upload, network/API/training use, arbitrary paths, traversal, symlinks, hardlinks, duplicate source hashes, bad/corrupt images, animated PNGs, unsupported profiles and portable source leakage.
- BP-49 writes private ingest/lifecycle/normalization/quality records, portable privacy-safe summaries and deletion tombstones; PNG quality is pixel-derived, while JPEG pixel quality remains structural-only until an approved decoder dependency is added.
- BP-50 derives visual observations from decoded project-authored raster fixture pixels rather than analytic T-shirt parameter polygons.
- BP-50 emits target-garment, person/body proxy, background and occlusion masks; torso/sleeve semantic parts; neckline/hem/cuff opening boundaries; required landmarks; confidence; missing-evidence/view-consistency records; and fixture metrics.
- BP-50 applies non-empty structured correction replay with include/exclude, landmark, left/right, view, semantic, confidence, occlusion and print-preservation operations, before/after hashes and stale-input rejection.
- BP-51 records required front/rear pairing plus optional left/right three-quarter roles; view orientation and scale evidence; cross-view garment identity; semantic identity tracks; deterministic D0 anchor/bbox registration; fused masks, landmarks, openings, confidence, missing evidence and contradiction records.
- BP-51 propagates the BP50 correction record into fused multiview evidence with before/after fusion hashes and cache/resume invalidation metadata.
- BP-51 adds a fail-closed Phase-2 quality gate that rejects missing rear views before expensive downstream fitting.
- Phase 2 is still D0/local synthetic-fixture-only. Learned segmentation, provider upload, private-user Gate P1, source pixel export, learned/geometric registration, image-conditioned fitting and Phase-2 completion remain incomplete.

Current blocking evidence:

- 23 non-manifold edges and 29 non-manifold vertices remain in the BP-46 stitched candidate.
- 8 duplicate faces remain in the BP-46 stitched candidate.
- 3 boundary components are detected rather than four proven semantic openings.
- Boundary graph contains branch vertices.
- Seam operation IDs include duplicates.
- Semantic opening assignment is not implemented.
- Stitched-shell binding coverage is incomplete.
- `selfIntersectionCheckStatus=not_run`.
- `tJunctionCheckStatus=not_run`.
- `inconsistentWindingCheckStatus=not_run`.
- `normalInversionCheckStatus=not_run`.
- `hiddenInternalComponentCheckStatus=not_run`.
- Full cloth motion, crack/sliding proof, runtime performance/memory profiling and mobile fallback negotiation are not implemented.

## Files And Functions Involved

- `closy-forge/src/closy_forge/visual_understanding/raster_parser.py`
- `closy-forge/src/closy_forge/visual_understanding/tshirt_observations.py`
- `closy-forge/src/closy_forge/visual_understanding/corrections.py`
- `closy-forge/src/closy_forge/visual_understanding/multiview_fusion.py`
- `closy-forge/src/closy_forge/capture/raster_sources.py`
- `closy-forge/src/closy_forge/reports/reporter.py`
- `closy-forge/src/closy_forge/pipeline/build_tshirt_demo.py`
- `closy-forge/src/closy_forge/cli/main.py`
- `closy-forge/src/closy_forge/contracts/schema_registry.py`
- `closy-forge/docs/MASTER_BLUEPRINT_PROGRESS.md`
- `closy-forge/docs/blueprint_coverage.json`
- `closy-forge/tests/unit/test_visual_understanding.py`
- `closy-forge/tests/integration/test_cli_and_package.py`
- `closy-forge/tests/golden/test_golden_demo.py`
- `closy-forge/tests/unit/test_blueprint_coverage.py`

## Checks Completed At Last Local BP51 Checkpoint

- Local `.venv\Scripts\python.exe -m ruff format --check .` reported 112 files already formatted.
- Local `.venv\Scripts\python.exe -m ruff check .` passed.
- Local `.venv\Scripts\python.exe -m mypy src` passed over 89 source files.
- Local `.venv\Scripts\python.exe -m closy_forge schemas check --schema-dir schemas/v1 --json` reported `{"issues":[],"status":"fresh"}`.
- Local `.venv\Scripts\python.exe -m pytest tests\unit\test_visual_understanding.py tests\integration\test_cli_and_package.py tests\golden\test_golden_demo.py -q` passed focused BP51/golden/integration coverage.
- Local `.venv\Scripts\python.exe -m pytest --collect-only -q` collected 184 Forge tests.
- Local `.venv\Scripts\python.exe -m pytest -q` passed the full 184-test Forge suite.
- Local deterministic package sanity built two temp packages, diffed them identical with 85 files each, validated with one formal `self_collision_not_run` warning, and reported digest `8b9c00555f2ad904154640c77399e167ecb6da929d0c707a677a6d49f3c7c94a`.

## Current Checks Not Yet Run After This Resume Update

- Blueprint coverage tests have not yet run for this BP51 ledger/coverage/resume update if this file is read before the next validation command.
- Remote CI has not yet run for BP51 implementation/evidence commits if this file is read before they are pushed.
- BP52 image-conditioned fitting is not implemented yet.

## Next Exact Command

```powershell
cd E:\apps\Closy\closy-forge
.\.venv\Scripts\python.exe -m pytest tests\unit\test_blueprint_coverage.py tests\unit\test_visual_understanding.py tests\integration\test_cli_and_package.py tests\golden\test_golden_demo.py -q
```

## Next Safe Action

Validate and commit the BP51 ledger/coverage/resume update, push normally to `codex/closy-forge-phase-2-capture`, update draft PR #2 with the BP51 facts, inspect the new Ubuntu/Windows checks, then branch Phase 3 and begin BP52 image-conditioned fitting only if remote evidence is green.
