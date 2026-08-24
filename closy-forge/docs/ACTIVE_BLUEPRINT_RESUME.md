# Active Blueprint Resume

This file is a recoverable checkpoint for the continuous Closy master-blueprint work. It records evidence ancestry and next actions without trying to cite its own future commit SHA.

## Current State

- Active blueprint checkpoint: `BP-50-PIXEL-PARSING-CORRECTIONS`
- Exact subtask: begin deterministic D0 pixel-derived garment/person/background parsing, T-shirt landmark/opening extraction and non-empty correction replay from BP49 normalized raster fixture evidence.
- Current branch: `codex/closy-forge-phase-2-capture`
- Parent branch: `codex/closy-forge-phase-0`
- Evidence implementation commit SHA: `fcf64dce8a2117c78df7d1a01f3cefad118b5093`
- Record based on SHA: `fcf64dce8a2117c78df7d1a01f3cefad118b5093`
- Draft PR: `https://github.com/jake-the-jake/Closy/pull/2`
- Parent draft PR: `https://github.com/jake-the-jake/Closy/pull/1`
- Last remote green evidence: GitHub Actions run `32700668662`; Ubuntu job `97351342200` and Windows job `97351342416` passed at commit `fcf64dce8a2117c78df7d1a01f3cefad118b5093`.
- Last remote matrix details: 110 files formatted, 87 mypy source files, 174 tests on each OS, fresh schemas, two identical 83-file package trees on each OS, package digest `b8e56370434d9275a17048eee5e94367de8736366ed2919e292a2b8acf8a4329`, package validation status `passed`.
- Formal package warning budget: exactly one package validator warning, `self_collision_not_run`.
- Clean acceptance report state: 13 checks with 9 pass, 1 fail, 2 warnings and 1 not-run; clean/canonical acceptance remains rejected.
- Current in-progress uncommitted work, if this file is read before the next commit: report/ledger truth-sync for clean-gate warning count display and BP49 remote evidence.
- Known unrelated local work outside this Forge slice remains unstaged and must be preserved: app avatar files, `metro.config.js`, and untracked `closy-forge/.tmp/`.

## Current BP-46/BP-47/BP-48/BP-49 Truth

- BP-46 still has `meshStitchOrWeldExecutionRun=true` backed by `stitch/logical_stitched_analysis_shell.json`, `render/stitched_shell.glb` and `reports/geometry_stitched_shell.json`.
- BP-46 still has `meshStitchOrWeldProven=false`, `acceptedForCleanProposal=false` and `acceptedForCanonical=false`.
- BP-47 adds deterministic SVG inspection artifacts and separated evidence tiers, but does not provide decoded raster visual fidelity, source/provider appearance comparison or signed human review.
- BP-48 adds persisted fallback GLB `NORMAL` and `VEC4` `TANGENT` accessors plus `reports/render_frame_pose_suite.json`.
- BP-48 validates four deterministic pose snapshots within the `1e-6` binding tolerance; after deterministic quantization the observed max pose binding error is `1e-09`.
- BP-48 records `renderTangentsPersistedAvailable=true`, `poseSuiteBindingEvidenceAvailable=true` and `acceptedForRuntimeFramePreview=true`.
- BP-48 keeps `acceptedForCleanProposal=false` and does not complete Phase 6 or Gate C3.
- BP-49 implements only `synthetic_fixture_raster_v1` for project-authored local PNG/JPEG fixtures. It rejects user imagery, provider upload, network/API/training use, arbitrary paths, traversal, symlinks, hardlinks, duplicate source hashes, bad/corrupt images, animated PNGs, unsupported profiles and portable source leakage.
- BP-49 writes private ingest/lifecycle/normalization/quality records, portable privacy-safe summaries and deletion tombstones; PNG quality is pixel-derived, while JPEG pixel quality remains structural-only until an approved decoder dependency is added.
- BP-50 masks, applied correction replay, multiview fusion and private-user Gate P1 remain incomplete.

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

- `closy-forge/src/closy_forge/capture/raster_sources.py`
- `closy-forge/src/closy_forge/reports/reporter.py`
- `closy-forge/src/closy_forge/pipeline/build_tshirt_demo.py`
- `closy-forge/src/closy_forge/proposals/geometry_clean_acceptance_gate.py`
- `closy-forge/src/closy_forge/validation/validator.py`
- `closy-forge/docs/MASTER_BLUEPRINT_PROGRESS.md`
- `closy-forge/docs/blueprint_coverage.json`
- `closy-forge/docs/raster-ingestion-v1.md`
- `closy-forge/tests/unit/test_raster_sources.py`
- `closy-forge/tests/unit/test_geometry_proposal.py`
- `closy-forge/tests/integration/test_cli_and_package.py`
- `closy-forge/tests/unit/test_blueprint_coverage.py`

## Checks Completed At Last Green Checkpoint

- Local `.venv\Scripts\python.exe -m pytest tests\unit\test_raster_sources.py -q` passed 21 raster tests after the symlink guard fix.
- Local `.venv\Scripts\python.exe -m ruff format --check .` reported 110 files already formatted.
- Local `.venv\Scripts\python.exe -m ruff check .` passed.
- Local `.venv\Scripts\python.exe -m mypy src` passed over 87 source files.
- Local `.venv\Scripts\python.exe -m closy_forge schemas check --schema-dir schemas/v1 --json` reported `{"issues":[],"status":"fresh"}`.
- Local `.venv\Scripts\python.exe -m pytest -q` passed the full Forge suite.
- Remote Forge run `32700668662` passed Ubuntu and Windows with 174 tests each, fresh schemas, deterministic package diff status `identical`, digest `b8e56370434d9275a17048eee5e94367de8736366ed2919e292a2b8acf8a4329`, and one formal package warning `self_collision_not_run`.

## Current Checks Not Yet Run After This Resume Update

- Focused report/coverage tests have not yet run for the clean-gate warning-count display change if this file is read before the next commit.
- Remote CI has not yet run for the report/ledger truth-sync commit if this file is read before that commit is pushed.
- BP50 pixel parsing and correction replay tests are not implemented yet.

## Next Exact Command

```powershell
cd E:\apps\Closy\closy-forge
.\.venv\Scripts\python.exe -m pytest tests\unit\test_geometry_proposal.py tests\integration\test_cli_and_package.py tests\unit\test_blueprint_coverage.py -q
```

## Next Safe Action

Validate and commit the clean-gate warning-count report/truth-sync change, push normally to `codex/closy-forge-phase-2-capture`, update draft PR #2 with the green run and truth-sync facts, inspect the new Ubuntu/Windows checks, then begin BP50 deterministic D0 pixel parsing and applied correction replay without crossing Gate P1 or promoting any clean/canonical geometry claim.
