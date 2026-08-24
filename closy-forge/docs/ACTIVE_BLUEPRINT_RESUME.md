# Active Blueprint Resume

This file is a recoverable checkpoint for the continuous Closy master-blueprint work. It records evidence ancestry and next actions without trying to cite its own future commit SHA.

## Current State

- Active blueprint checkpoint: `BP-52-IMAGE-CONDITIONED-FITTING`
- Exact subtask: deterministic D0 image-conditioned T-shirt fitting now consumes BP51 fused multiview evidence on the Phase-3 fitting branch.
- Current branch: `codex/closy-forge-phase-3-fitting`
- Parent branch: `codex/closy-forge-phase-2-capture`
- Latest implementation commit SHA: `e23820eddaf6d6599a3b125ee1a083dc97ef4acd`
- Latest implementation commit subject: `Add BP52 image-conditioned fitting`
- Record based on SHA: `c6c94f7ac2fcbde388c9e2b70dd69ae802d7add3`; this resume file itself belongs to the follow-up remote-evidence truth-sync commit.
- Draft PR: `https://github.com/jake-the-jake/Closy/pull/3`, draft/open, stacked on `codex/closy-forge-phase-2-capture`.
- Parent draft PR: `https://github.com/jake-the-jake/Closy/pull/2`
- Last remote green evidence inherited from Phase 2: GitHub Actions run `32719446390`; Ubuntu job `97407535366` and Windows job `97407535566` passed at commit `f6051f9b8ae79e47d47fe1dee7c2cf8da2f1521e`.
- Last remote Phase-2 matrix details: each OS ran 112 format-checked files, 89 mypy source files, 185 tests, fresh schemas, identical 85-file package trees, digest `8b9c00555f2ad904154640c77399e167ecb6da929d0c707a677a6d49f3c7c94a`, and validation with only `self_collision_not_run`.
- Current local BP52 evidence after `e23820e`: `ruff format --check .` reported 112 files already formatted; `ruff check .` passed; `mypy src` passed over 89 source files; schema export wrote 49 schemas; schema check reported `{"issues":[],"status":"fresh"}`; focused BP52 unit/integration/golden/corruption tests passed; full `pytest -q` exited 0 after collecting 189 tests; two OS-temp package builds were byte-identical with 85 files each and digest `1b9638ea05962b7611540ab03f46ddc99a5417871586ef5cf4388b2323657790`; `packages diff`, `validate --json` and `report --json` passed with one formal warning.
- A full local `pytest -q` started immediately after BP52 implementation exposed one variant-prior regression in `test_bounded_tshirt_variants_validate_and_keep_stable_semantics`; the committed BP52 fix separated prior movement from the `maximumParameterDeltaMeters` threshold, and the final clean local suite above now passes.
- Last remote BP52 evidence before this truth-sync update: GitHub Actions run `32728354755` passed at commit `c6c94f7ac2fcbde388c9e2b70dd69ae802d7add3`; Ubuntu job `97434656635` passed in 6m57s and Windows job `97434656119` passed in 10m5s. Each OS ran 112 format-checked files, 89 mypy source files, 189 tests, fresh schemas, identical 85-file package trees and validation/report with only `self_collision_not_run`.
- Formal package warning budget: exactly one package validator warning, `self_collision_not_run`.
- Clean acceptance report state: 13 checks with 9 pass, 1 fail, 2 warnings and 1 not-run; clean/canonical acceptance remains rejected.
- Current in-progress uncommitted work, if this file is read before the next commit: BP52 remote-evidence truth-sync update.
- Known unrelated local work outside this Forge slice remains unstaged and must be preserved: app avatar files, `metro.config.js`, and untracked `closy-forge/.tmp/`.

## Current BP-46/BP-47/BP-48/BP-49/BP-50/BP-51/BP-52 Truth

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
- BP-52 records deterministic D0 image-conditioned fitting from BP51 fused multiview evidence.
- BP-52 fit report `fit.image_conditioned_tshirt_multiview_d0_v1` hash-links visual observations, multiview fusion, fused evidence and corrected visual record hashes.
- BP-52 declares bounded T-shirt parameter space and keeps prior parameters explicitly separate from observed evidence. Prior movement is reported as `priorPenaltyMeters`; it is not treated as expected ground truth.
- BP-52 reports multiview silhouette IoU `0.939980`, boundary error `0.018125`, landmark error `0.002972`, opening alignment error `0.002106`, camera/body alignment error `0.002000`, seam/ease penalty `0.000516` and confidence-weighted loss `0.019326` for the D0 reference fixture.
- BP-52 emits a four-step optimisation trace, convergence diagnostics, multiple hypotheses, held-out rear-view evaluation and deterministic perturbation evaluation.
- BP-52 truthfully records settled-render/drape comparison as `not_run_dependency_pending`.
- Phase 3 remains partial. BP52 is D0/local synthetic-raster-fixture-only and does not enable private-user fitting, learned prediction, differentiable rendering, depth fitting or production cloth fitting.

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

- `closy-forge/src/closy_forge/fitting/tshirt_fit.py`
- `closy-forge/src/closy_forge/pipeline/build_tshirt_demo.py`
- `closy-forge/src/closy_forge/reports/reporter.py`
- `closy-forge/src/closy_forge/validation/validator.py`
- `closy-forge/src/closy_forge/contracts/schema_registry.py`
- `closy-forge/schemas/v1/tshirt-fit-report.schema.json`
- `closy-forge/schemas/v1/garment-manifest.schema.json`
- `closy-forge/docs/MASTER_BLUEPRINT_PROGRESS.md`
- `closy-forge/docs/blueprint_coverage.json`
- `closy-forge/tests/unit/test_tshirt_fit.py`
- `closy-forge/tests/unit/test_blueprint_coverage.py`
- `closy-forge/tests/integration/test_cli_and_package.py`
- `closy-forge/tests/integration/test_determinism_and_variants.py`
- `closy-forge/tests/golden/test_golden_demo.py`
- `closy-forge/tests/corruption/test_corrupted_packages.py`

## Checks Completed At Last Local BP52 Checkpoint

- Local `.venv\Scripts\python.exe -m ruff format --check .` reported 112 files already formatted.
- Local `.venv\Scripts\python.exe -m ruff check .` passed.
- Local `.venv\Scripts\python.exe -m mypy src` passed over 89 source files.
- Local `.venv\Scripts\python.exe -m closy_forge schemas export --output schemas\v1` exported 49 schemas.
- Local `.venv\Scripts\python.exe -m closy_forge schemas check --schema-dir schemas\v1 --json` reported `{"issues":[],"status":"fresh"}`.
- Local `.venv\Scripts\python.exe -m pytest tests\unit\test_blueprint_coverage.py -q` passed.
- Local `.venv\Scripts\python.exe -m pytest tests\unit\test_tshirt_fit.py tests\integration\test_cli_and_package.py tests\integration\test_determinism_and_variants.py::test_bounded_tshirt_variants_validate_and_keep_stable_semantics tests\golden\test_golden_demo.py tests\corruption\test_corrupted_packages.py::test_tshirt_fit_multiview_source_hash_mismatch_is_rejected tests\corruption\test_corrupted_packages.py::test_tshirt_fit_fixture_expected_parameters_are_rejected -q` passed.
- Local `.venv\Scripts\python.exe -m pytest tests\unit\test_blueprint_coverage.py tests\unit\test_tshirt_fit.py tests\integration\test_cli_and_package.py tests\golden\test_golden_demo.py tests\corruption\test_corrupted_packages.py -q` passed.
- Local `.venv\Scripts\python.exe -m pytest -q` exited 0; collect-only evidence counted 189 tests.
- Two local smoke packages built at OS temp paths, produced identical package trees with 85 files each, and both reported digest `1b9638ea05962b7611540ab03f46ddc99a5417871586ef5cf4388b2323657790`.
- Local `.venv\Scripts\python.exe -m closy_forge packages diff <temp-a> <temp-b> --json` reported `{"status":"identical","leftFileCount":85,"rightFileCount":85}` with no changed or missing files.
- Local `.venv\Scripts\python.exe -m closy_forge validate <temp-a> --json` reported status `passed`, counts `fatal=0`, `error=0`, `warning=1`, and issue code `self_collision_not_run`.
- Local `.venv\Scripts\python.exe -m closy_forge report <temp-a> --json` reported BP52 fitting accepted with silhouette IoU `0.93998`, boundary error `0.018125`, landmark RMS `0.002972`, opening alignment `0.002106`, confidence-weighted loss `0.019326`, held-out status `pass`, perturbation status `pass`, and four optimisation iterations.

## Current Checks Not Yet Run After This Resume Update

- Remote CI has not yet run for this BP52 remote-evidence truth-sync commit if this file is read before it is pushed.

## Next Exact Command

```powershell
cd E:\apps\Closy\closy-forge
.\.venv\Scripts\python.exe -m pytest tests\unit\test_blueprint_coverage.py -q
```

## Next Safe Action

Validate this BP52 remote-evidence truth-sync update, commit it, push normally to `codex/closy-forge-phase-3-fitting`, update draft PR #3, inspect remote Ubuntu/Windows Forge CI, then branch Phase 4 for BP-53 only after the truth-sync commit is also remote green.
