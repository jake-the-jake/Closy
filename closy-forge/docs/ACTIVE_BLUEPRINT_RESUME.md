# Active Blueprint Resume

This file is a recoverable checkpoint for the continuous Closy master-blueprint work. It records evidence ancestry and next actions without trying to cite its own future commit SHA.

## Current State

- Active blueprint checkpoint: `BP-53-SOURCE-TEXTURE-PBR-RECOVERY`
- Exact subtask: deterministic D0 source-view texture projection, generated atlas metadata, mobile-safe PBR maps and controlled inpainting guardrails from raster-backed fitting evidence.
- Current branch: `codex/closy-forge-phase-4-texture`
- Parent branch: `codex/closy-forge-phase-3-fitting`
- Phase-4 branch point: `bb496684f4ba9c41fdfe5c69bc272679aaecafac`
- Latest implementation commit SHA: `9fc004d429d9187bfd427586ca43af65e54ec2f5`
- Latest implementation commit subject: `Add BP53 source texture recovery`
- Record based on SHA: `cbd675ea93dc46600db3ca4a1932c8a642888b9e`; this resume file itself belongs to the follow-up BP53 remote-evidence truth-sync commit.
- Draft PR: `https://github.com/jake-the-jake/Closy/pull/4`, draft/open, stacked on `codex/closy-forge-phase-3-fitting`.
- Parent draft PR: `https://github.com/jake-the-jake/Closy/pull/3`, draft/open, stacked on `codex/closy-forge-phase-2-capture`.
- Grandparent draft PR: `https://github.com/jake-the-jake/Closy/pull/2`, draft/open, stacked on `codex/closy-forge-phase-0`.
- Last remote green evidence inherited from Phase 3: GitHub Actions run `32729539416`; Ubuntu job `97438405296` and Windows job `97438405597` passed at commit `bb496684f4ba9c41fdfe5c69bc272679aaecafac`.
- Last remote Phase-3 matrix details: each OS ran 112 format-checked files, 89 mypy source files, 189 tests, fresh schemas, identical 85-file package trees, digest `1b9638ea05962b7611540ab03f46ddc99a5417871586ef5cf4388b2323657790`, and validation/report with only `self_collision_not_run`.
- Current local BP53 evidence after `9fc004d`: `ruff format --check .` reported 112 files already formatted; `ruff check .` passed; `mypy src` passed over 89 source files; schema export wrote 49 schemas; schema check reported `{"issues":[],"status":"fresh"}`; focused BP53 texture/integration/golden/corruption tests passed; full `pytest -q` exited 0 after 192 collected tests; two OS-temp package builds were byte-identical with 89 files each and digest `a36fd735db6545216e700516ff8a76ad1b9689677d78ae8fb930995c5f0a168e`; `packages diff`, `validate --json` and `report --json` passed with one formal warning.
- Last remote BP53 evidence before this truth-sync update: GitHub Actions run `32741055846` passed at commit `cbd675ea93dc46600db3ca4a1932c8a642888b9e`; Ubuntu job `97475348702` passed in 5m8s and Windows job `97475348519` passed in 7m47s. Each OS ran 112 format-checked files, 89 mypy source files, 192 tests, fresh schemas, identical 89-file package trees, digest `a36fd735db6545216e700516ff8a76ad1b9689677d78ae8fb930995c5f0a168e`, and validation/report with only `self_collision_not_run`.
- Current BP53 package texture summary: `sourceTextureAvailable=true`, `generatedAtlasAvailable=true`, `textureProjectionRun=true`, `sourceProjectionCount=16`, `visibleProjectionCount=16`, `meanVisibleConfidence=0.925`, `pbrSourceBackedMapCount=1`, `pbrPlaceholderMapCount=5`.
- Formal package warning budget: exactly one package validator warning, `self_collision_not_run`.
- Clean acceptance report state remains rejected; clean/canonical acceptance remains false.
- Current in-progress uncommitted work, if this file is read before the next commit: BP53 remote-evidence truth-sync update.
- Known unrelated local work outside this Forge slice remains unstaged and must be preserved: app avatar files, `metro.config.js`, and untracked `closy-forge/.tmp/`.

## Current BP-46/BP-47/BP-48/BP-49/BP-50/BP-51/BP-52/BP-53 Truth

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
- BP-53 records deterministic D0 source-view texture/PBR recovery from BP49 raster records, BP50 pixel observations, BP51 multiview fusion and BP52 fitted evidence.
- BP-53 texture identity `texture.source_projected_tshirt_identity_d0_v1` hash-links source/fusion/fitted inputs and emits four canonical texture artifacts: `textures/source_projection.json`, `textures/generated_atlas.json`, `textures/pbr_material_maps.json` and `textures/conventional_fallback_materials.json`.
- BP-53 records privacy-safe `colorEvidence`, source-view projection coordinates, seam-aware projection/blending metadata, visible-region confidence, logo/print preservation evidence, controlled-inpainting rejection of visible-evidence overwrite, source-backed jersey material maps and truthful placeholder maps for hidden/unseen regions.
- Phase 4 remains partial. BP53 is D0/local synthetic-raster-fixture-only and does not enable private-user texture recovery, raw pixel export, learned texture completion, source/provider/human visual-fidelity acceptance, clean geometry promotion or canonical acceptance.

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

- `closy-forge/src/closy_forge/appearance/texture_identity.py`
- `closy-forge/src/closy_forge/visual_understanding/raster_parser.py`
- `closy-forge/src/closy_forge/pipeline/build_tshirt_demo.py`
- `closy-forge/src/closy_forge/reports/reporter.py`
- `closy-forge/src/closy_forge/validation/validator.py`
- `closy-forge/src/closy_forge/contracts/schema_registry.py`
- `closy-forge/src/closy_forge/proposals/geometry_material_uv_transfer.py`
- `closy-forge/schemas/v1/texture-identity.schema.json`
- `closy-forge/schemas/v1/garment-manifest.schema.json`
- `closy-forge/docs/MASTER_BLUEPRINT_PROGRESS.md`
- `closy-forge/docs/blueprint_coverage.json`
- `closy-forge/tests/unit/test_texture_identity.py`
- `closy-forge/tests/unit/test_blueprint_coverage.py`
- `closy-forge/tests/integration/test_cli_and_package.py`
- `closy-forge/tests/golden/test_golden_demo.py`
- `closy-forge/tests/corruption/test_corrupted_packages.py`

## Checks Completed At Last Local BP53 Checkpoint

- Local `.venv\Scripts\ruff.exe format --check .` reported 112 files already formatted.
- Local `.venv\Scripts\ruff.exe check .` passed.
- Local `.venv\Scripts\mypy.exe src` passed over 89 source files.
- Local `.venv\Scripts\closy-forge.exe schemas export --output schemas\v1` exported 49 schemas.
- Local `.venv\Scripts\closy-forge.exe schemas check --schema-dir schemas\v1 --json` reported `{"issues":[],"status":"fresh"}`.
- Local `.venv\Scripts\pytest.exe tests\unit\test_texture_identity.py tests\integration\test_cli_and_package.py tests\golden\test_golden_demo.py tests\corruption\test_corrupted_packages.py -q` passed.
- Local `.venv\Scripts\pytest.exe -q` exited 0; collect-only evidence counted 192 tests.
- Two local smoke packages built at OS temp paths, produced identical package trees with 89 files each, and both reported digest `a36fd735db6545216e700516ff8a76ad1b9689677d78ae8fb930995c5f0a168e`.
- Local `.venv\Scripts\closy-forge.exe packages diff <temp-a> <temp-b> --json` reported `{"status":"identical","leftFileCount":89,"rightFileCount":89}` with no changed or missing files.
- Local `.venv\Scripts\closy-forge.exe validate <temp-a> --json` reported status `passed`, counts `fatal=0`, `error=0`, `warning=1`, and issue code `self_collision_not_run`.
- Local `.venv\Scripts\closy-forge.exe report <temp-a> --json` reported BP53 texture source available, projection run, 16 source projections, 16 visible projections, mean visible confidence `0.925`, one source-backed PBR map and five placeholder maps.

## Current Checks Not Yet Run After This Resume Update

- Remote CI has not yet run for this BP53 remote-evidence truth-sync commit if this file is read before it is pushed.

## Next Exact Command

```powershell
cd E:\apps\Closy\closy-forge
.\.venv\Scripts\pytest.exe tests\unit\test_blueprint_coverage.py -q
```

## Next Safe Action

Validate this BP53 remote-evidence truth-sync update, commit it, push normally to `codex/closy-forge-phase-4-texture`, update the Phase-4 draft PR against `codex/closy-forge-phase-3-fitting`, inspect remote Ubuntu/Windows Forge CI, then freeze Phase 4 after remote green and branch `codex/closy-forge-foundation-proof-closeout`.
