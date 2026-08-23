# Active Blueprint Resume

This file is a recoverable checkpoint for the continuous Closy master-blueprint work. It records evidence ancestry and next actions without trying to cite its own future commit SHA.

## Current State

- Active blueprint checkpoint: `BP-49-RASTER-INGESTION-PRIVACY`
- Exact subtask: begin local PNG/JPEG raster ingestion with consent/privacy/deletion records and deterministic normalization while preserving the synthetic demo fallback.
- Current branch: `codex/closy-forge-phase-0`
- Evidence commit SHA: `0e743bbc930ab3f52169022163c2ce5a426719d8`
- Record based on SHA: `0e743bbc930ab3f52169022163c2ce5a426719d8`
- Draft PR: `https://github.com/jake-the-jake/Closy/pull/1`
- Last remote green evidence before this resume record: GitHub Actions run `32665478422`, Ubuntu and Windows Forge Python 3.11 jobs passed at commit `f4bdc736e8343fb573ef2df83a371bf90eec51d2`.
- Current remote evidence for BP48: pending until the BP48 implementation and ledger commits are pushed.
- Last local package digest: `30daa00bf9dcd84568cb668b4db1abab3a529da7312df4af422358645c3213b3`
- Last local package inventory: 79 manifest-inventoried files; two temp package trees were byte-identical with 83 files per side.

## Current BP-46/BP-47/BP-48 Truth

- BP-46 still has `meshStitchOrWeldExecutionRun=true` backed by `stitch/logical_stitched_analysis_shell.json`, `render/stitched_shell.glb` and `reports/geometry_stitched_shell.json`.
- BP-46 still has `meshStitchOrWeldProven=false`, `acceptedForCleanProposal=false` and `acceptedForCanonical=false`.
- BP-47 adds deterministic SVG inspection artifacts and separated evidence tiers, but does not provide decoded raster visual fidelity, source/provider appearance comparison or signed human review.
- BP-48 adds persisted fallback GLB `NORMAL` and `VEC4` `TANGENT` accessors plus `reports/render_frame_pose_suite.json`.
- BP-48 records `renderTangentsPersistedAvailable=true`, `poseSuiteBindingEvidenceAvailable=true` and `acceptedForRuntimeFramePreview=true`.
- BP-48 keeps `acceptedForCleanProposal=false` and does not complete Phase 6 or Gate C3.

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

- `closy-forge/src/closy_forge/geometry/frame_attributes.py`
- `closy-forge/src/closy_forge/geometry/glb_io.py`
- `closy-forge/src/closy_forge/rendering/frame_pose_suite.py`
- `closy-forge/src/closy_forge/pipeline/build_tshirt_demo.py`
- `closy-forge/src/closy_forge/validation/validator.py`
- `closy-forge/src/closy_forge/contracts/schema_registry.py`
- `closy-forge/schemas/v1/render-frame-pose-suite.schema.json`
- `closy-forge/schemas/v1/garment-manifest.schema.json`
- `closy-forge/tests/unit/test_render_frame_pose_suite.py`
- `closy-forge/tests/golden/expected_demo_summary.json`
- `closy-forge/docs/MASTER_BLUEPRINT_PROGRESS.md`
- `closy-forge/docs/blueprint_coverage.json`
- `closy-forge/tests/unit/test_blueprint_coverage.py`

## Checks Completed After This Resume Update

- `python -m closy_forge schemas export --output schemas/v1`
- `python -m pytest tests/unit/test_render_frame_pose_suite.py tests/golden/test_golden_demo.py tests/unit/test_schema_freshness.py -q`
- `python -m ruff format --check .`
- `python -m ruff check .`
- `python -m mypy src`
- `python -m pytest -q`
- `python -m pytest --collect-only -q` collected 151 Forge tests.
- deterministic temp-path `demo build-tshirt` produced digest `30daa00bf9dcd84568cb668b4db1abab3a529da7312df4af422358645c3213b3` twice.
- `python -m closy_forge packages diff` reported two temp packages identical, with 83 files on each side.
- `python -m closy_forge validate` passed with the single current package validation warning `self_collision_not_run`.
- `python -m closy_forge report` confirmed the same package digest, 79 inventoried files, BP48 frame/pose evidence and rejected clean-acceptance state.
- `python -m closy_forge schemas check --schema-dir schemas/v1 --json` reported fresh schemas.

## Current Checks Not Yet Run After This Resume Update

- Remote CI for BP48 implementation and ledger commits is pending until those commits are pushed.
- BP49 raster ingestion tests are not implemented yet.

## Next Exact Command

```powershell
cd E:\apps\Closy\closy-forge
.\.venv\Scripts\python.exe -m pytest tests\unit\test_blueprint_coverage.py tests\unit\test_render_frame_pose_suite.py -q
```

## Next Safe Action

Commit and push the BP48 ledger/resume update, verify PR #1 CI on Ubuntu and Windows, then begin BP49 local raster ingestion/privacy evidence without promoting any BP46/BP47/BP48 clean or canonical acceptance claim.
